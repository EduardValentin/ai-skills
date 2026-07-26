"""Pinned Docker Sandboxes lifecycle for model-backed evaluations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import select
import signal
import shutil
import stat
import subprocess
import threading
import time
import tomllib
from typing import Iterator, Literal, Protocol

from scripts.ai_skills_lib.runtime_environment import CASE_OWNED_ENVIRONMENT_NAMES
from scripts.ai_skills_lib.secret_patterns import (
    SECRET_PATTERNS,
    bounded_redacted_runtime_text,
)


WorkerRole = Literal["actor", "judge"]
_MAX_DOCKER_CODEX_PROFILE_BYTES = 1024 * 1024
_PROFILE_READ_CHUNK_BYTES = 64 * 1024

# Canonical OAuth profile emitted by the Codex kit bundled with pinned sbx v0.35.0.
_PINNED_DOCKER_CODEX_CONFIG_BYTES = b"""\
# Codex configuration for Docker sandbox
# This configuration enables "yolo mode" - no approvals, full access

approval_policy = "never"
sandbox_mode = "danger-full-access"
mcp_oauth_credentials_store = "file"

model_provider = "sandboxd"

[model_providers.sandboxd]
name = "Sandbox Proxy"
base_url = "https://chatgpt.com/backend-api/codex"
experimental_bearer_token = "oai-oat01-proxy-managed"
requires_openai_auth = false
"""
_PINNED_DOCKER_CODEX_AUTH_BYTES = b'{\n  "OPENAI_API_KEY": "proxy-managed"\n}\n'

_EXPECTED_DOCKER_CODEX_CONFIG_SHAPE: dict[str, object] = {
    "approval_policy": "never",
    "sandbox_mode": "danger-full-access",
    "mcp_oauth_credentials_store": "file",
    "model_provider": "sandboxd",
    "model_providers": {
        "sandboxd": {
            "name": "Sandbox Proxy",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "experimental_bearer_token": "oai-oat01-proxy-managed",
            "requires_openai_auth": False,
        }
    },
}
_EXPECTED_DOCKER_CODEX_AUTH_SHAPE: dict[str, object] = {
    "OPENAI_API_KEY": "proxy-managed",
}

CLEANUP_FAILURE_MAXIMUM_BYTES = 8192
CLEANUP_TARGET_FAILURE_MAXIMUM_BYTES = 640
OWNERSHIP_MARKER_FILENAME = ".ai-skills-sandbox-owner"
OWNERSHIP_NONCE_BYTES = 32
CASE_TMPFS_SIZE_BYTES = 268435456
CASE_TMPFS_NR_INODES = 32768
PROCESS_KILL_GRACE_SECONDS = 2.0
PROCESS_GROUP_PROOF_SECONDS = 1.0
PROCESS_DRAIN_JOIN_SECONDS = 1.0
PROCESS_POLL_SECONDS = 0.01
_SUBPROCESS_POPEN_TYPE = subprocess.Popen

CASE_FILESYSTEM_PROBE_SCRIPT = r"""import os
import pathlib
import re
import stat
import sys

case_root = os.path.normpath(sys.argv[1])
expected_source = sys.argv[2]
expected_bytes = int(sys.argv[3])
expected_inodes = int(sys.argv[4])
covered_paths = tuple(os.path.normpath(path) for path in sys.argv[5:])
mount_points = (
    (case_root, "/"),
    ("/tmp", "/tmp"),
    ("/var/tmp", "/.system-var-tmp"),
    ("/dev/shm", "/.system-dev-shm"),
    ("/run/lock", "/.system-run-lock"),
    ("/run/secrets", "/.system-run-secrets"),
)

def decode_mount_field(value):
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )

entries = {}
all_entries = []
for line in pathlib.Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
    fields = line.split()
    try:
        separator = fields.index("-")
    except ValueError:
        continue
    if len(fields) <= separator + 3:
        continue
    mount_point = os.path.normpath(decode_mount_field(fields[4]))
    entry = (
        os.path.normpath(decode_mount_field(fields[3])),
        fields[2],
        fields[separator + 1],
        decode_mount_field(fields[separator + 2]),
        set(fields[5].split(",")) | set(fields[separator + 3].split(",")),
    )
    entries.setdefault(mount_point, []).append(entry)
    all_entries.append((mount_point, entry))

root_device = os.stat(case_root).st_dev
root_mount_device = None
for mount_point, expected_root in mount_points:
    candidates = entries.get(mount_point, ())
    if not candidates:
        raise SystemExit(f"required case mount is absent: {mount_point}")
    mounted_root, mount_device, filesystem, source, options = candidates[-1]
    if (
        mounted_root != expected_root
        or filesystem != "tmpfs"
        or source not in (expected_source, "tmpfs")
        or not {"rw", "nosuid", "nodev"}.issubset(options)
    ):
        raise SystemExit(f"case mount does not match the pinned tmpfs: {mount_point}")
    if root_mount_device is None:
        root_mount_device = mount_device
    elif mount_device != root_mount_device:
        raise SystemExit(f"case mount does not share the case tmpfs: {mount_point}")
    matching_mounts = [
        candidate
        for candidate in candidates
        if candidate[0] == expected_root
        and candidate[1] == mount_device
        and candidate[2] == "tmpfs"
        and candidate[3] in (expected_source, "tmpfs")
    ]
    if len(matching_mounts) != 1 or matching_mounts[0] != candidates[-1]:
        raise SystemExit(f"case mount is unexpectedly stacked: {mount_point}")
    filesystem_stats = os.statvfs(mount_point)
    if filesystem_stats.f_blocks * filesystem_stats.f_frsize != expected_bytes:
        raise SystemExit(f"case mount byte quota does not match: {mount_point}")
    if filesystem_stats.f_files != expected_inodes:
        raise SystemExit(f"case mount inode quota does not match: {mount_point}")
    if os.stat(mount_point).st_dev != root_device:
        raise SystemExit(f"case mount does not share the case quota: {mount_point}")

protected_roots = tuple(path for path, _ in mount_points)
for mount_point, _ in all_entries:
    if any(
        mount_point != protected_root
        and mount_point.startswith(protected_root.rstrip("/") + "/")
        for protected_root in protected_roots
    ):
        raise SystemExit(f"unexpected nested mount beneath case quota: {mount_point}")

if stat.S_IMODE(os.stat(case_root).st_mode) != 0o555:
    raise SystemExit("case tmpfs root mode does not match")
for path in covered_paths:
    if os.stat(path).st_dev != root_device:
        raise SystemExit(f"writable case path escapes the case quota: {path}")
"""

CASE_FILESYSTEM_CLEANUP_SCRIPT = r"""import os
import pathlib
import re
import subprocess
import sys

expected_source = sys.argv[1]
case_root = os.path.normpath(sys.argv[2])
bridge_mount = os.path.normpath(sys.argv[3])
raw_case_mounts = tuple(os.path.normpath(path) for path in sys.argv[4:])
if not raw_case_mounts or len(raw_case_mounts) % 2:
    raise SystemExit("case filesystem cleanup received an invalid mount contract")
case_mounts = raw_case_mounts[::2]
case_mount_roots = raw_case_mounts[1::2]
bridge_path = pathlib.Path(bridge_mount)
expected_bridge_root = pathlib.Path("/run/ai-skills-evals") / expected_source
if bridge_path != expected_bridge_root / "host":
    raise SystemExit("case host bridge is outside the runner-owned hierarchy")
if len(set(case_mounts)) != len(case_mounts) or len(set(case_mount_roots)) != len(
    case_mount_roots
):
    raise SystemExit("case filesystem cleanup received an invalid mount contract")

def decode_mount_field(value):
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )

def read_mounts():
    entries = []
    for line in pathlib.Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        if len(fields) <= separator + 2:
            continue
        entries.append(
            {
                "id": fields[0],
                "parent": fields[1],
                "device": fields[2],
                "root": os.path.normpath(decode_mount_field(fields[3])),
                "path": os.path.normpath(decode_mount_field(fields[4])),
                "filesystem": fields[separator + 1],
                "source": decode_mount_field(fields[separator + 2]),
            }
        )
    return entries

def mounts_at(path, entries):
    return [entry for entry in entries if entry["path"] == path]

def unmount_top(path):
    before = mounts_at(path, read_mounts())
    if not before:
        return
    mounted_id = before[-1]["id"]
    subprocess.run(("umount", "--", path), check=False)
    after = mounts_at(path, read_mounts())
    if after and after[-1]["id"] == mounted_id:
        raise SystemExit(f"mount could not be cleared: {path}")

def expose_mount(path, expected_id):
    for _ in range(16):
        candidates = mounts_at(path, read_mounts())
        if not candidates:
            raise SystemExit(f"expected case mount disappeared: {path}")
        if candidates[-1]["id"] == expected_id:
            return
        if not any(candidate["id"] == expected_id for candidate in candidates):
            raise SystemExit(f"unexpected mount replaced the case mount: {path}")
        unmount_top(path)
    raise SystemExit(f"case mount stack is too deep: {path}")

def descendant_depth(entry, ancestor_id, by_id):
    depth = 0
    current = entry
    visited = set()
    while current["parent"] in by_id and current["parent"] not in visited:
        visited.add(current["parent"])
        depth += 1
        if current["parent"] == ancestor_id:
            return depth
        current = by_id[current["parent"]]
    return None

def clear_mount_tree(path, expected_entry):
    expose_mount(path, expected_entry["id"])
    for _ in range(128):
        entries = read_mounts()
        by_id = {entry["id"]: entry for entry in entries}
        descendants = []
        for entry in entries:
            depth = descendant_depth(entry, expected_entry["id"], by_id)
            if depth is not None:
                descendants.append((depth, entry))
        if not descendants:
            break
        _, deepest = max(
            descendants,
            key=lambda item: (item[0], item[1]["path"].count("/")),
        )
        unmount_top(deepest["path"])
    else:
        raise SystemExit(f"nested case mount tree is too deep: {path}")
    expose_mount(path, expected_entry["id"])
    unmount_top(path)
    if any(
        entry["id"] == expected_entry["id"]
        for entry in read_mounts()
    ):
        raise SystemExit(f"case mount remains mounted: {path}")

entries = read_mounts()
case_candidates = [
    entry
    for entry in mounts_at(case_root, entries)
    if entry["root"] == "/"
    and entry["filesystem"] == "tmpfs"
]
if case_candidates:
    case_entry = case_candidates[-1]
    case_device = case_entry["device"]
    expected_system_mounts = []
    entries = read_mounts()
    for mount_point, mounted_root in zip(case_mounts, case_mount_roots, strict=True):
        candidates = [
            entry
            for entry in mounts_at(mount_point, entries)
            if entry["device"] == case_device
            and entry["root"] == mounted_root
            and entry["filesystem"] == "tmpfs"
        ]
        if candidates:
            expected_system_mounts.append((mount_point, candidates[-1]))
    for mount_point, expected_entry in reversed(expected_system_mounts):
        clear_mount_tree(mount_point, expected_entry)
    clear_mount_tree(case_root, case_entry)

for _ in range(16):
    if not mounts_at(bridge_mount, read_mounts()):
        break
    unmount_top(bridge_mount)
else:
    raise SystemExit("case host bridge mount stack is too deep")

for directory in (bridge_path, expected_bridge_root):
    try:
        directory.rmdir()
    except FileNotFoundError:
        pass
"""

CASE_PRIVILEGE_LOCKDOWN_SCRIPT = r"""import os
import pathlib
import stat

def pin_zero(path, *, required):
    target = pathlib.Path(path)
    if not target.exists():
        if required:
            raise SystemExit(f"required namespace control is unavailable: {path}")
        return
    target.write_text("0\n", encoding="ascii")
    if target.read_text(encoding="ascii").strip() != "0":
        raise SystemExit(f"namespace control did not remain disabled: {path}")

pin_zero("/proc/sys/user/max_user_namespaces", required=True)
pin_zero("/proc/sys/kernel/unprivileged_userns_clone", required=False)

fuse_path = "/dev/fuse"
if os.path.lexists(fuse_path):
    metadata = os.lstat(fuse_path)
    if stat.S_ISDIR(metadata.st_mode):
        raise SystemExit("/dev/fuse is unexpectedly a directory")
    os.unlink(fuse_path)
if os.path.lexists(fuse_path):
    raise SystemExit("/dev/fuse remains available")
"""

CASE_PRIVILEGE_PROBE_SCRIPT = r"""import ctypes
import errno
import os
import pathlib
import sys

mountpoint = os.fsencode(sys.argv[1])
if pathlib.Path("/proc/sys/user/max_user_namespaces").read_text(
    encoding="ascii"
).strip() != "0":
    raise SystemExit("unprivileged user namespaces are not disabled")
clone_control = pathlib.Path("/proc/sys/kernel/unprivileged_userns_clone")
if clone_control.exists() and clone_control.read_text(encoding="ascii").strip() != "0":
    raise SystemExit("unprivileged user namespace cloning is not disabled")
if os.path.lexists("/dev/fuse"):
    raise SystemExit("FUSE device remains available")

libc = ctypes.CDLL(None, use_errno=True)
if libc.mount(b"tmpfs", mountpoint, b"tmpfs", 0, b"size=4096,nr_inodes=4") == 0:
    libc.umount2(mountpoint, 2)
    raise SystemExit("case UID can create mounts")
if ctypes.get_errno() not in (errno.EPERM, errno.EACCES):
    raise SystemExit("case UID mount denial is ambiguous")

CLONE_NEWUSER = 0x10000000
if libc.unshare(CLONE_NEWUSER) == 0:
    raise SystemExit("case UID can create a user namespace")
if ctypes.get_errno() not in (errno.EPERM, errno.EACCES, errno.EINVAL, errno.ENOSYS):
    raise SystemExit("case UID user namespace denial is ambiguous")
"""

WORKER_MOUNT_PROTECT_SCRIPT = r"""import os
import pathlib
import re
import stat
import subprocess
import sys

worker_root = pathlib.Path(os.path.normpath(sys.argv[1]))
if not worker_root.is_absolute() or worker_root == pathlib.Path("/"):
    raise SystemExit("worker mount root is invalid")
metadata = worker_root.lstat()
if not stat.S_ISDIR(metadata.st_mode) or worker_root.is_symlink():
    raise SystemExit("worker mount root is not a directory")

def decode(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)

def entries():
    found = []
    for line in pathlib.Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        if len(fields) <= separator + 3:
            continue
        if pathlib.Path(os.path.normpath(decode(fields[4]))) == worker_root:
            found.append(set(fields[5].split(",")))
    return found

before = entries()
if len(before) == 1:
    subprocess.run(("mount", "--bind", str(worker_root), str(worker_root)), check=True)
elif len(before) != 2:
    raise SystemExit("worker mount root does not have a safe bind depth")
subprocess.run(("mount", "-o", "remount,bind,ro", str(worker_root)), check=True)
after = entries()
if len(after) != 2 or "ro" not in after[-1] or "rw" in after[-1]:
    raise SystemExit("worker mount root is not protected by one read-only bind")
"""

WORKER_MOUNT_RESTORE_SCRIPT = r"""import os
import pathlib
import re
import stat
import subprocess
import sys

worker_root = pathlib.Path(os.path.normpath(sys.argv[1]))
if not worker_root.is_absolute() or worker_root == pathlib.Path("/"):
    raise SystemExit("worker mount root is invalid")
metadata = worker_root.lstat()
if not stat.S_ISDIR(metadata.st_mode) or worker_root.is_symlink():
    raise SystemExit("worker mount root is not a directory")

def decode(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)

def entries():
    found = []
    for line in pathlib.Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        if len(fields) <= separator + 3:
            continue
        if pathlib.Path(os.path.normpath(decode(fields[4]))) == worker_root:
            found.append(set(fields[5].split(",")))
    return found

before = entries()
if not before:
    raise SystemExit("worker mount root is not mounted")
if "ro" in before[-1]:
    subprocess.run(("mount", "-o", "remount,bind,rw", str(worker_root)), check=True)
after = entries()
if len(after) != len(before) or "rw" not in after[-1] or "ro" in after[-1]:
    raise SystemExit("worker mount root was not restored read-write")
"""

CASE_CGROUP_SETUP_SCRIPT = r"""import os
import pathlib
import re
import stat
import sys

cgroup = pathlib.Path(sys.argv[1])
cgroup_root = pathlib.Path("/sys/fs/cgroup")
expected_parent = cgroup_root / "ai-skills-evals"
if cgroup.parent != expected_parent or re.fullmatch(r"[a-zA-Z0-9.+-]+", cgroup.name) is None:
    raise SystemExit("case cgroup path is outside the runner-owned hierarchy")

def decode_mount_field(value):
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )

cgroup_mounts = []
for line in pathlib.Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
    fields = line.split()
    try:
        separator = fields.index("-")
    except ValueError:
        continue
    if len(fields) <= separator + 1:
        continue
    if os.path.normpath(decode_mount_field(fields[4])) == str(cgroup_root):
        cgroup_mounts.append((
            os.path.normpath(decode_mount_field(fields[3])),
            fields[separator + 1],
            set(fields[5].split(",")) | set(fields[separator + 3].split(",")),
        ))
if len(cgroup_mounts) != 1 or cgroup_mounts[0][0] != "/" or cgroup_mounts[0][1] != "cgroup2":
    raise SystemExit("a unique cgroup v2 mount is unavailable")
if "rw" not in cgroup_mounts[0][2]:
    raise SystemExit("the cgroup v2 mount is not writable")

expected_parent.mkdir(mode=0o700, exist_ok=True)
parent_metadata = expected_parent.lstat()
if (
    not stat.S_ISDIR(parent_metadata.st_mode)
    or parent_metadata.st_uid != 0
    or stat.S_IMODE(parent_metadata.st_mode) != 0o700
):
    raise SystemExit("runner-owned cgroup parent is not root-only")
if cgroup.exists():
    raise SystemExit("case cgroup already exists")
cgroup.mkdir(mode=0o700)
cgroup_metadata = cgroup.lstat()
if (
    not stat.S_ISDIR(cgroup_metadata.st_mode)
    or cgroup_metadata.st_uid != 0
    or stat.S_IMODE(cgroup_metadata.st_mode) != 0o700
):
    raise SystemExit("case cgroup is not root-only")
required = ("cgroup.procs", "cgroup.events", "cgroup.freeze", "cgroup.kill")
if any(not (cgroup / name).is_file() for name in required):
    raise SystemExit("required cgroup v2 lifecycle controls are unavailable")

def events():
    parsed = {}
    for line in (cgroup / "cgroup.events").read_text(encoding="ascii").splitlines():
        name, value = line.split()
        parsed[name] = value
    return parsed

if (cgroup / "cgroup.procs").read_text(encoding="ascii").strip():
    raise SystemExit("new case cgroup is unexpectedly populated")
if events().get("populated") != "0":
    raise SystemExit("new case cgroup population cannot be proven empty")
(cgroup / "cgroup.freeze").write_text("0\n", encoding="ascii")
if events().get("frozen") != "0":
    raise SystemExit("new case cgroup could not be proven unfrozen")
"""

CASE_CGROUP_EXEC_SCRIPT = r"""import ctypes
import os
import pathlib
import sys

cgroup = pathlib.Path(sys.argv[1])
uid = int(sys.argv[2])
command = sys.argv[3:]
if not command or uid <= 0:
    raise SystemExit("case cgroup execution contract is incomplete")
for name in ("cgroup.procs", "cgroup.events", "cgroup.freeze", "cgroup.kill"):
    if not (cgroup / name).is_file():
        raise SystemExit("case cgroup lifecycle control disappeared")
(cgroup / "cgroup.procs").write_text(f"{os.getpid()}\n", encoding="ascii")
members = {
    int(value)
    for value in (cgroup / "cgroup.procs").read_text(encoding="ascii").split()
}
if os.getpid() not in members:
    raise SystemExit("case process did not enter its cgroup")

PR_SET_NO_NEW_PRIVS = 38
if ctypes.CDLL(None, use_errno=True).prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
    raise SystemExit("case process could not enable no-new-privileges")
os.setgroups([])
os.setresgid(uid, uid, uid)
os.setresuid(uid, uid, uid)
if os.getuid() != uid or os.getgid() != uid or os.getgroups():
    raise SystemExit("case process identity transition failed")
status = {}
for line in pathlib.Path("/proc/self/status").read_text(encoding="ascii").splitlines():
    if ":" in line:
        name, value = line.split(":", 1)
        status[name] = value.strip()
for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"):
    value = status.get(name)
    if value is None:
        raise SystemExit("case process capability state is unavailable")
if any(int(status[name], 16) != 0 for name in ("CapInh", "CapPrm", "CapEff", "CapAmb")):
    raise SystemExit("case process retained Linux capabilities")
os.execvp(command[0], command)
"""

CASE_CGROUP_TERMINATE_SCRIPT = r"""import pathlib
import sys
import time

cgroup = pathlib.Path(sys.argv[1])
timeout_seconds = float(sys.argv[2])
if timeout_seconds <= 0:
    raise SystemExit("case cgroup cleanup timeout is invalid")
for name in ("cgroup.procs", "cgroup.events", "cgroup.freeze", "cgroup.kill"):
    if not (cgroup / name).is_file():
        raise SystemExit("required cgroup v2 lifecycle control is unavailable")

def events():
    parsed = {}
    for line in (cgroup / "cgroup.events").read_text(encoding="ascii").splitlines():
        name, value = line.split()
        parsed[name] = value
    return parsed

def is_empty():
    return (
        events().get("populated") == "0"
        and not (cgroup / "cgroup.procs").read_text(encoding="ascii").strip()
    )

deadline = time.monotonic() + timeout_seconds
if is_empty():
    time.sleep(0.01)
    if is_empty():
        raise SystemExit(0)

(cgroup / "cgroup.freeze").write_text("1\n", encoding="ascii")
while events().get("frozen") != "1":
    if time.monotonic() >= deadline:
        raise SystemExit("case cgroup could not be frozen")
    time.sleep(0.01)

(cgroup / "cgroup.kill").write_text("1\n", encoding="ascii")
while True:
    state = events()
    members = (cgroup / "cgroup.procs").read_text(encoding="ascii").strip()
    if state.get("populated") == "0" and not members:
        break
    if time.monotonic() >= deadline:
        raise SystemExit("case cgroup population could not be proven empty")
    time.sleep(0.01)
if events().get("populated") != "0" or (cgroup / "cgroup.procs").read_text(
    encoding="ascii"
).strip():
    raise SystemExit("case cgroup emptiness changed during verification")
"""

CASE_CGROUP_REMOVE_SCRIPT = r"""import pathlib
import sys

cgroup = pathlib.Path(sys.argv[1])
if not cgroup.is_dir():
    raise SystemExit("case cgroup disappeared before verified removal")
events = {}
for line in (cgroup / "cgroup.events").read_text(encoding="ascii").splitlines():
    name, value = line.split()
    events[name] = value
if events.get("populated") != "0" or (cgroup / "cgroup.procs").read_text(
    encoding="ascii"
).strip():
    raise SystemExit("populated case cgroup cannot be removed")
cgroup.rmdir()
if cgroup.exists():
    raise SystemExit("case cgroup removal could not be verified")
"""

OWNERSHIP_MARKER_PROBE_SCRIPT = """import hashlib
import os
import stat
import sys

path = sys.argv[1]
flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(path, flags)
try:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 256:
        raise SystemExit("ownership marker is not a bounded regular file")
    content = os.read(descriptor, 257)
    if len(content) != metadata.st_size:
        raise SystemExit("ownership marker changed while being read")
    sys.stdout.write(hashlib.sha256(content).hexdigest())
finally:
    os.close(descriptor)
"""

IPC_CLEANUP_SCRIPT = """import pathlib
import subprocess
import sys

uid = int(sys.argv[1])
proc_root = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path("/proc")
queue_root = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else pathlib.Path("/dev/mqueue")
tables = (("shm", "shmid", "-m"), ("msg", "msqid", "-q"), ("sem", "semid", "-s"))

for table, _, _ in tables:
    if not (proc_root / "sysvipc" / table).is_file():
        raise SystemExit("SysV IPC inspection surface is unavailable")

mountinfo = proc_root / "self" / "mountinfo"
if not mountinfo.is_file():
    raise SystemExit("mqueue inspection surface is unavailable")
has_mqueue_mount = False
for line in mountinfo.read_text(encoding="utf-8").splitlines():
    fields = line.split()
    try:
        separator = fields.index("-")
    except ValueError:
        continue
    if len(fields) > separator + 1 and fields[4] == str(queue_root):
        has_mqueue_mount = fields[separator + 1] == "mqueue"
        break
if not queue_root.is_dir() or not has_mqueue_mount:
    raise SystemExit("mqueue inspection surface is unavailable")

def owned_ids():
    found = []
    for table, identifier_name, flag in tables:
        path = proc_root / "sysvipc" / table
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue
        columns = lines[0].split()
        identifier_index = columns.index(identifier_name)
        uid_index = columns.index("uid")
        creator_uid_index = columns.index("cuid")
        for line in lines[1:]:
            values = line.split()
            if uid in (int(values[uid_index]), int(values[creator_uid_index])):
                found.append((flag, values[identifier_index]))
    return found

for flag, identifier in owned_ids():
    subprocess.run(("ipcrm", flag, identifier), check=True)

for queue in queue_root.iterdir():
    if queue.lstat().st_uid == uid:
        queue.unlink()

if owned_ids():
    raise SystemExit("UID-owned SysV IPC state remains")
if any(queue.lstat().st_uid == uid for queue in queue_root.iterdir()):
    raise SystemExit("UID-owned POSIX message queues remain")
"""

CATALOG_RENAME_PROBE_SCRIPT = """import errno
import os
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
try:
    os.rename(source, target)
except OSError as error:
    if error.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
        raise
    if not source.is_dir() or target.exists():
        raise SystemExit("catalog rename probe left an unexpected filesystem state")
else:
    os.rename(target, source)
    raise SystemExit("catalog directory entry is replaceable by the case user")
"""

DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT = """import errno
import os
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
if not target.parent.is_dir() or target.exists():
    raise SystemExit("write-denial probe target is not clean")
try:
    os.mkdir(target, 0o700)
except OSError as error:
    if error.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
        raise
    if target.exists():
        raise SystemExit("write-denial probe left an unexpected filesystem entry")
else:
    os.rmdir(target)
    raise SystemExit("directory accepts writes from the case user")
"""

ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT = r"""import os
import pathlib
import re
import stat
import sys

if len(sys.argv) < 3:
    raise SystemExit("root filesystem probe contract is incomplete")

probe_root = os.path.realpath(sys.argv[1])
mountinfo_path = pathlib.Path(sys.argv[2])
allowed_writable_roots = tuple(
    os.path.normpath(os.path.realpath(path))
    for path in sys.argv[3:]
)
if len(set(allowed_writable_roots)) != len(allowed_writable_roots):
    raise SystemExit("allowed writable filesystem roots are duplicated")

def is_within(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")

if any(not is_within(path, probe_root) for path in allowed_writable_roots):
    raise SystemExit("allowed writable filesystem root escapes the probe root")

def decode_mount_field(value):
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )

try:
    mountinfo_lines = mountinfo_path.read_text(encoding="utf-8").splitlines()
except OSError as error:
    raise SystemExit("filesystem mount table is unavailable") from error

mounts = []
for line_number, line in enumerate(mountinfo_lines, start=1):
    fields = line.split()
    try:
        separator = fields.index("-")
    except ValueError as error:
        raise SystemExit(
            f"filesystem mount table entry is malformed: line {line_number}"
        ) from error
    if len(fields) <= separator + 3 or len(fields) < 6:
        raise SystemExit(
            f"filesystem mount table entry is incomplete: line {line_number}"
        )
    mount_point = os.path.normpath(decode_mount_field(fields[4]))
    if not os.path.isabs(mount_point):
        raise SystemExit(
            f"filesystem mount point is not absolute: line {line_number}"
        )
    mounts.append(
        (
            mount_point,
            fields[separator + 1],
            set(fields[5].split(",")) | set(fields[separator + 3].split(",")),
        )
    )

visible_mounts = {}
for mount in mounts:
    mount_point = mount[0]
    if not is_within(mount_point, probe_root):
        continue
    visible_mounts[mount_point] = mount
if probe_root not in visible_mounts:
    raise SystemExit("probe root is absent from the filesystem mount table")

for allowed_root in allowed_writable_roots:
    mount = visible_mounts.get(allowed_root)
    if mount is None:
        raise SystemExit(f"allowed writable filesystem mount is absent: {allowed_root}")
    options = mount[2]
    if "rw" not in options or "ro" in options:
        raise SystemExit(
            f"allowed writable filesystem mount is not writable: {allowed_root}"
        )

pseudo_filesystems = {
    "/proc": {
        "binfmt_misc",
        "proc",
        "tmpfs",
    },
    "/sys": {
        "bpf",
        "cgroup",
        "cgroup2",
        "configfs",
        "debugfs",
        "efivarfs",
        "fusectl",
        "pstore",
        "securityfs",
        "sysfs",
        "tmpfs",
        "tracefs",
    },
    "/dev": {
        "devpts",
        "devtmpfs",
        "hugetlbfs",
        "mqueue",
        "tmpfs",
    },
}

def pseudo_root_for(path):
    for root in pseudo_filesystems:
        if is_within(path, root):
            return root
    return None

for mount_point, filesystem, _ in visible_mounts.values():
    if mount_point in allowed_writable_roots:
        continue
    if any(
        mount_point != allowed_root and is_within(mount_point, allowed_root)
        for allowed_root in allowed_writable_roots
    ):
        raise SystemExit(
            f"unexpected nested mount beneath case tmpfs: {mount_point}"
        )
    pseudo_root = pseudo_root_for(mount_point)
    if pseudo_root is not None:
        if filesystem not in pseudo_filesystems[pseudo_root]:
            raise SystemExit(
                f"unsupported pseudo-filesystem mount: {mount_point} ({filesystem})"
            )
        continue
    try:
        metadata = os.stat(mount_point, follow_symlinks=False)
    except OSError as error:
        if os.access(os.path.dirname(mount_point), os.X_OK):
            raise SystemExit(
                f"cannot inspect actor-traversable filesystem mount: {mount_point}"
            ) from error
        continue
    if stat.S_ISDIR(metadata.st_mode):
        writable = os.access(mount_point, os.W_OK | os.X_OK)
    elif stat.S_ISREG(metadata.st_mode):
        writable = os.access(mount_point, os.W_OK)
    else:
        writable = False
    if writable:
        raise SystemExit(
            f"writable filesystem mount outside case tmpfs: {mount_point}"
        )

skipped_roots = (*allowed_writable_roots, *pseudo_filesystems)
pending = [probe_root]
while pending:
    current = pending.pop()
    if current != probe_root and any(is_within(current, root) for root in skipped_roots):
        continue
    try:
        metadata = os.stat(current, follow_symlinks=False)
    except OSError:
        continue
    if not stat.S_ISDIR(metadata.st_mode):
        continue
    if os.access(current, os.W_OK | os.X_OK):
        raise SystemExit(f"writable root filesystem path: {current}")
    try:
        entries = os.scandir(current)
    except OSError as error:
        if os.access(current, os.X_OK):
            raise SystemExit(
                f"cannot inspect actor-traversable root filesystem directory: {current}"
            ) from error
        continue
    with entries:
        for entry in entries:
            try:
                child = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(child.st_mode):
                pending.append(entry.path)
            elif (
                stat.S_ISREG(child.st_mode)
                and os.access(entry.path, os.W_OK)
            ):
                raise SystemExit(f"writable root filesystem file: {entry.path}")
"""

PUBLIC_SKILL_CATALOG_PROBE_SCRIPT = """import errno
import os
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1])
system_skills = root / ".system"
metadata = root.lstat()
if not stat.S_ISDIR(metadata.st_mode) or root.is_symlink():
    raise SystemExit("public skill catalog root is invalid")
if not metadata.st_mode & stat.S_ISVTX or not os.access(root, os.W_OK | os.X_OK):
    raise SystemExit("public skill catalog root is not a writable sticky directory")
if not system_skills.is_dir() or system_skills.is_symlink():
    raise SystemExit("Codex system skill directory is invalid")

catalog_probe = root / ".catalog-write-probe"
system_probe = root / ".system-replace-probe"
if catalog_probe.exists() or system_probe.exists():
    raise SystemExit("skill catalog probe target is not clean")
catalog_probe.mkdir(mode=0o700)
catalog_probe.rmdir()
os.rename(system_skills, system_probe)
os.rename(system_probe, system_skills)

for entry in root.iterdir():
    if entry.name == ".system":
        continue
    if entry.is_symlink() or not entry.is_dir():
        raise SystemExit("public skill entry is not a real directory")
    rename_probe = root / f".{entry.name}.rename-probe"
    write_probe = entry / ".write-probe"
    if rename_probe.exists() or write_probe.exists():
        raise SystemExit("public skill probe target is not clean")
    try:
        os.rename(entry, rename_probe)
    except OSError as error:
        if error.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
            raise
        if not entry.is_dir() or rename_probe.exists():
            raise SystemExit("public skill rename probe changed the catalog")
    else:
        os.rename(rename_probe, entry)
        raise SystemExit("public skill entry is replaceable by the case user")
    try:
        os.mkdir(write_probe, 0o700)
    except OSError as error:
        if error.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
            raise
        if write_probe.exists():
            raise SystemExit("public skill write probe changed the skill")
    else:
        os.rmdir(write_probe)
        raise SystemExit("public skill entry accepts writes from the case user")
"""


class ManifestError(ValueError):
    """The immutable evaluation runtime manifest is invalid."""


class SandboxRuntimeError(RuntimeError):
    """Docker Sandboxes could not establish a trustworthy execution boundary."""


@dataclass(frozen=True)
class ProcessTerminationOutcome:
    """Observable proof that a started host command no longer has live state."""

    process_started: bool
    leader_reaped: bool
    process_group_absent: bool
    drains_stopped: bool

    @property
    def fully_terminated_and_reaped(self) -> bool:
        return (
            self.process_started
            and self.leader_reaped
            and self.process_group_absent
            and self.drains_stopped
        )


PROCESS_NOT_STARTED = ProcessTerminationOutcome(
    process_started=False,
    leader_reaped=False,
    process_group_absent=True,
    drains_stopped=True,
)
PROCESS_FULLY_TERMINATED = ProcessTerminationOutcome(
    process_started=True,
    leader_reaped=True,
    process_group_absent=True,
    drains_stopped=True,
)
_PROCESS_OUTCOME_ATTRIBUTE = "_ai_skills_process_termination_outcome"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    lifecycle_failure: str | None = None
    process_outcome: ProcessTerminationOutcome = PROCESS_FULLY_TERMINATED


def _attach_process_outcome(
    error: BaseException,
    outcome: ProcessTerminationOutcome,
) -> None:
    try:
        setattr(error, _PROCESS_OUTCOME_ATTRIBUTE, outcome)
    except BaseException:
        pass


def process_termination_outcome(
    error: BaseException,
) -> ProcessTerminationOutcome | None:
    outcome = getattr(error, _PROCESS_OUTCOME_ATTRIBUTE, None)
    return outcome if isinstance(outcome, ProcessTerminationOutcome) else None


class ProcessRunner(Protocol):
    def run(self, argv: tuple[str, ...], *, timeout_seconds: int) -> CommandResult:
        """Run one bounded host process and expose its verified termination outcome."""


class SubprocessRunner:
    """Production process boundary used by the sandbox adapter."""

    def __init__(self, maximum_output_bytes: int) -> None:
        self._maximum_output_bytes = maximum_output_bytes

    def run(self, argv: tuple[str, ...], *, timeout_seconds: int) -> CommandResult:
        process: subprocess.Popen[bytes] | None = None
        drains: list[tuple[threading.Thread, object]] = []
        try:
            stdout_buffer = bytearray()
            stderr_buffer = bytearray()
            truncation = {"stdout": False, "stderr": False}
            timed_out = False
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            stdout_budget = self._maximum_output_bytes // 2
            stderr_budget = self._maximum_output_bytes - stdout_budget

            def drain(stream, buffer: bytearray, budget: int, key: str) -> None:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        return
                    remaining = budget - len(buffer)
                    if remaining > 0:
                        buffer.extend(chunk[:remaining])
                    if len(chunk) > max(remaining, 0):
                        truncation[key] = True

            for stream, buffer, budget, key in (
                (process.stdout, stdout_buffer, stdout_budget, "stdout"),
                (process.stderr, stderr_buffer, stderr_budget, "stderr"),
            ):
                if stream is None:
                    raise SandboxRuntimeError("host process output pipe was not created")
                thread = threading.Thread(
                    target=drain,
                    args=(stream, buffer, budget, key),
                    daemon=True,
                )
                drains.append((thread, stream))
                thread.start()

            try:
                if isinstance(process, _SUBPROCESS_POPEN_TYPE):
                    completed = self._wait_for_leader_exit_without_reaping(
                        process,
                        timeout_seconds,
                    )
                    if not completed:
                        raise subprocess.TimeoutExpired(argv, timeout_seconds)
                    outcome = self._settle_process(
                        process,
                        drains,
                        leader_reaped=False,
                        terminate_group=True,
                    )
                    if process.returncode is None:
                        raise SandboxRuntimeError(
                            "host process leader completion could not be reaped"
                        )
                    returncode = process.returncode
                else:
                    returncode = process.wait(timeout=timeout_seconds)
                    outcome = self._settle_process(
                        process,
                        drains,
                        leader_reaped=True,
                        terminate_group=False,
                    )
            except subprocess.TimeoutExpired:
                timed_out = True
                returncode = 124
                outcome = self._settle_process(
                    process,
                    drains,
                    leader_reaped=False,
                    terminate_group=True,
                )
            if not outcome.fully_terminated_and_reaped:
                error = SandboxRuntimeError(
                    "host process group termination and reaping could not be proven"
                )
                _attach_process_outcome(error, outcome)
                raise error
            return CommandResult(
                returncode=returncode,
                stdout=self._decode(stdout_buffer),
                stderr=self._decode(stderr_buffer),
                timed_out=timed_out,
                stdout_truncated=truncation["stdout"],
                stderr_truncated=truncation["stderr"],
                process_outcome=outcome,
            )
        except BaseException as error:
            if process is None:
                _attach_process_outcome(error, PROCESS_NOT_STARTED)
                raise
            outcome = self._settle_process_safely(process, drains)
            _attach_process_outcome(error, outcome)
            raise

    @staticmethod
    def _decode(value: bytes) -> str:
        return value.decode("utf-8", errors="replace")

    def _settle_process(
        self,
        process: subprocess.Popen[bytes],
        drains: Sequence[tuple[threading.Thread, object]],
        *,
        leader_reaped: bool,
        terminate_group: bool,
    ) -> ProcessTerminationOutcome:
        if terminate_group and not leader_reaped and process.returncode is None:
            # Complete every destructive group signal before wait() can reap the
            # leader and make its numeric process-group identity reusable.
            self._signal_process_group(process.pid, signal.SIGTERM)
            self._signal_process_group(process.pid, signal.SIGKILL)
            leader_reaped = self._bounded_wait(
                process,
                PROCESS_KILL_GRACE_SECONDS,
            )

        group_absent = self._prove_process_group_absent(process.pid)
        drains_stopped = self._stop_drain_threads(process, drains)
        return ProcessTerminationOutcome(
            process_started=True,
            leader_reaped=leader_reaped or process.returncode is not None,
            process_group_absent=group_absent,
            drains_stopped=drains_stopped,
        )

    def _settle_process_safely(
        self,
        process: subprocess.Popen[bytes],
        drains: Sequence[tuple[threading.Thread, object]],
    ) -> ProcessTerminationOutcome:
        for _ in range(2):
            try:
                return self._settle_process(
                    process,
                    drains,
                    leader_reaped=process.returncode is not None,
                    terminate_group=True,
                )
            except BaseException:
                pass
        return ProcessTerminationOutcome(
            process_started=True,
            leader_reaped=process.returncode is not None,
            process_group_absent=False,
            drains_stopped=False,
        )

    @staticmethod
    def _bounded_wait(
        process: subprocess.Popen[bytes],
        maximum_seconds: float,
    ) -> bool:
        deadline = time.monotonic() + maximum_seconds
        while process.returncode is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                break
            except BaseException:
                SubprocessRunner._pause(
                    min(PROCESS_POLL_SECONDS, max(0.0, remaining))
                )
            else:
                return True
        return process.returncode is not None

    @staticmethod
    def _wait_for_leader_exit_without_reaping(
        process: subprocess.Popen[bytes],
        maximum_seconds: float,
    ) -> bool:
        waitid_names = ("waitid", "P_PID", "WEXITED", "WNOHANG", "WNOWAIT")
        if all(hasattr(os, name) for name in waitid_names):
            return SubprocessRunner._waitid_for_leader_exit(
                process,
                maximum_seconds,
            )
        kqueue_names = (
            "kqueue",
            "kevent",
            "KQ_FILTER_PROC",
            "KQ_EV_ADD",
            "KQ_EV_ONESHOT",
            "KQ_NOTE_EXIT",
        )
        if all(hasattr(select, name) for name in kqueue_names):
            queue = select.kqueue()
            try:
                event = select.kevent(
                    process.pid,
                    filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                    fflags=select.KQ_NOTE_EXIT,
                )
                return bool(queue.control((event,), 1, maximum_seconds))
            finally:
                queue.close()
        raise SandboxRuntimeError(
            "host cannot observe process completion without reaping its leader"
        )

    @staticmethod
    def _waitid_for_leader_exit(
        process: subprocess.Popen[bytes],
        maximum_seconds: float,
    ) -> bool:
        deadline = time.monotonic() + maximum_seconds
        flags = os.WEXITED | os.WNOHANG | os.WNOWAIT
        while True:
            result = os.waitid(os.P_PID, process.pid, flags)
            if result is not None and getattr(result, "si_pid", process.pid) == process.pid:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            SubprocessRunner._pause(min(PROCESS_POLL_SECONDS, remaining))

    @classmethod
    def _prove_process_group_absent(cls, process_group_id: int) -> bool:
        deadline = time.monotonic() + PROCESS_GROUP_PROOF_SECONDS
        while True:
            if not cls._process_group_exists(process_group_id):
                return True
            if time.monotonic() >= deadline:
                return False
            cls._pause(PROCESS_POLL_SECONDS)

    @staticmethod
    def _process_group_exists(process_group_id: int) -> bool:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return False
        except BaseException:
            return True
        return True

    @staticmethod
    def _signal_process_group(process_group_id: int, signal_number: int) -> None:
        try:
            os.killpg(process_group_id, signal_number)
        except BaseException:
            pass

    @classmethod
    def _stop_drain_threads(
        cls,
        process: subprocess.Popen[bytes],
        drains: Sequence[tuple[threading.Thread, object]],
    ) -> bool:
        cls._join_drain_threads(drains)
        for thread, stream in drains:
            if cls._thread_is_alive(thread):
                try:
                    os.close(stream.fileno())
                except BaseException:
                    pass
        cls._join_drain_threads(drains)
        stopped = not any(cls._thread_is_alive(thread) for thread, _ in drains)
        threads_by_stream = {id(stream): thread for thread, stream in drains}
        for stream in (process.stdout, process.stderr):
            if stream is None:
                continue
            thread = threads_by_stream.get(id(stream))
            if thread is not None and cls._thread_is_alive(thread):
                continue
            try:
                stream.close()
            except BaseException:
                stopped = False
        return stopped

    @staticmethod
    def _join_drain_threads(
        drains: Sequence[tuple[threading.Thread, object]],
    ) -> None:
        for thread, _ in drains:
            deadline = time.monotonic() + (
                PROCESS_DRAIN_JOIN_SECONDS / max(1, len(drains))
            )
            while SubprocessRunner._thread_is_alive(thread):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                try:
                    thread.join(timeout=remaining)
                except BaseException:
                    SubprocessRunner._pause(
                        min(PROCESS_POLL_SECONDS, max(0.0, remaining))
                    )
                    continue
                break

    @staticmethod
    def _thread_is_alive(thread: threading.Thread) -> bool:
        try:
            return thread.is_alive()
        except BaseException:
            return True

    @staticmethod
    def _pause(seconds: float) -> None:
        try:
            time.sleep(seconds)
        except BaseException:
            pass


@dataclass(frozen=True)
class NetworkPolicyPin:
    preset: str
    policy_id: str
    rules_sha256: str
    required_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class SbxPin:
    version: str
    revision: str
    network_policy: NetworkPolicyPin


@dataclass(frozen=True)
class CodexPin:
    agent: str
    version: str
    template: str
    allow_login_shell: bool
    fixture_environment_scope: str
    exec_flags: tuple[str, ...]


@dataclass(frozen=True)
class AuthenticationPin:
    service: str
    mode: str
    copy_host_credentials: bool


@dataclass(frozen=True)
class WorkerSettings:
    default_concurrency: int
    maximum_concurrency: int
    cpus: int
    memory: str
    reuse_scope: str
    separate_actor_and_judge_pools: bool


@dataclass(frozen=True)
class RuntimeLimits:
    preflight_timeout_seconds: int
    actor_timeout_seconds: int
    judge_timeout_seconds: int
    maximum_captured_output_bytes: int


@dataclass(frozen=True)
class MockServerPin:
    version: str
    image: str
    digest: str
    bind: str
    reuse_scope: str
    ca_scope: str
    maximum_expected_requests: int
    bundled_default_ca_sha256: str
    schema_release: str
    schema_source: str
    schema_path: Path
    schema_sha256: str
    reset_per_case: tuple[str, ...]
    passthrough: bool

    @property
    def image_reference(self) -> str:
        return f"{self.image}@{self.digest}"


@dataclass(frozen=True)
class CaseIsolation:
    fresh_worker_projection: bool
    fresh_home: bool
    fresh_workspace: bool
    fresh_codex_home_from_proxy_stubs: bool
    fresh_tmpdir: bool
    ephemeral_harness_session: bool
    durable_results_mounted_into_actor: bool
    writable_filesystem: str
    maximum_writable_bytes: int
    maximum_writable_inodes: int
    reset_failure: str


@dataclass(frozen=True)
class EvalRuntimeManifest:
    schema_version: int
    runtime: str
    sbx: SbxPin
    codex: CodexPin
    authentication: AuthenticationPin
    workers: WorkerSettings
    limits: RuntimeLimits
    docker_engine: str
    mockserver: MockServerPin
    case_isolation: CaseIsolation

    @classmethod
    def load(cls, path: Path) -> EvalRuntimeManifest:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ManifestError(f"cannot read runtime manifest: {error}") from error
        root = _mapping(raw, "runtime manifest")
        _expect_keys(
            root,
            {
                "schema_version",
                "runtime",
                "sbx",
                "codex",
                "authentication",
                "workers",
                "limits",
                "fixtures",
                "case_isolation",
            },
            "runtime manifest",
        )

        sbx_raw = _section(root, "sbx", {"version", "revision", "network_policy"})
        network_policy_raw = _section(
            sbx_raw,
            "network_policy",
            {"preset", "policy_id", "rules_sha256", "required_rule_ids"},
        )
        codex_raw = _section(
            root,
            "codex",
            {
                "agent",
                "version",
                "template",
                "allow_login_shell",
                "fixture_environment_scope",
                "exec_flags",
            },
        )
        auth_raw = _section(root, "authentication", {"service", "mode", "copy_host_credentials"})
        workers_raw = _section(
            root,
            "workers",
            {
                "default_concurrency",
                "maximum_concurrency",
                "cpus",
                "memory",
                "reuse_scope",
                "separate_actor_and_judge_pools",
            },
        )
        limits_raw = _section(
            root,
            "limits",
            {
                "preflight_timeout_seconds",
                "actor_timeout_seconds",
                "judge_timeout_seconds",
                "maximum_captured_output_bytes",
            },
        )
        fixtures_raw = _section(root, "fixtures", {"docker_engine", "mockserver"})
        mockserver_raw = _section(
            fixtures_raw,
            "mockserver",
            {
                "version",
                "image",
                "digest",
                "bind",
                "reuse_scope",
                "ca_scope",
                "maximum_expected_requests",
                "bundled_default_ca_sha256",
                "schema",
                "reset_per_case",
                "passthrough",
            },
        )
        schema_raw = _section(mockserver_raw, "schema", {"release", "source", "path", "sha256"})
        isolation_raw = _section(
            root,
            "case_isolation",
            {
                "fresh_worker_projection",
                "fresh_home",
                "fresh_workspace",
                "fresh_codex_home_from_proxy_stubs",
                "fresh_tmpdir",
                "ephemeral_harness_session",
                "durable_results_mounted_into_actor",
                "writable_filesystem",
                "maximum_writable_bytes",
                "maximum_writable_inodes",
                "reset_failure",
            },
        )

        template = _string(codex_raw, "template")
        if not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", template):
            raise ManifestError("codex.template must be a fully qualified digest-bound image reference")
        mockserver_digest = _string(mockserver_raw, "digest")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", mockserver_digest):
            raise ManifestError("fixtures.mockserver.digest must be an immutable sha256 digest")

        maximum_concurrency = _integer(workers_raw, "maximum_concurrency")
        default_concurrency = _integer(workers_raw, "default_concurrency")
        if maximum_concurrency not in range(1, 5):
            raise ManifestError("workers.maximum_concurrency must be between 1 and 4")
        if default_concurrency not in range(1, maximum_concurrency + 1):
            raise ManifestError("workers.default_concurrency must not exceed maximum_concurrency")

        manifest = cls(
            schema_version=_integer(root, "schema_version"),
            runtime=_string(root, "runtime"),
            sbx=SbxPin(
                version=_plain_version(sbx_raw, "version"),
                revision=_hex_string(sbx_raw, "revision", 40),
                network_policy=NetworkPolicyPin(
                    preset=_string(network_policy_raw, "preset"),
                    policy_id=_string(network_policy_raw, "policy_id"),
                    rules_sha256=_hex_string(network_policy_raw, "rules_sha256", 64),
                    required_rule_ids=_string_tuple(network_policy_raw, "required_rule_ids"),
                ),
            ),
            codex=CodexPin(
                agent=_string(codex_raw, "agent"),
                version=_plain_version(codex_raw, "version"),
                template=template,
                allow_login_shell=_boolean(codex_raw, "allow_login_shell"),
                fixture_environment_scope=_string(codex_raw, "fixture_environment_scope"),
                exec_flags=_string_tuple(codex_raw, "exec_flags"),
            ),
            authentication=AuthenticationPin(
                service=_string(auth_raw, "service"),
                mode=_string(auth_raw, "mode"),
                copy_host_credentials=_boolean(auth_raw, "copy_host_credentials"),
            ),
            workers=WorkerSettings(
                default_concurrency=default_concurrency,
                maximum_concurrency=maximum_concurrency,
                cpus=_integer(workers_raw, "cpus"),
                memory=_string(workers_raw, "memory"),
                reuse_scope=_string(workers_raw, "reuse_scope"),
                separate_actor_and_judge_pools=_boolean(workers_raw, "separate_actor_and_judge_pools"),
            ),
            limits=RuntimeLimits(
                preflight_timeout_seconds=_positive_integer(limits_raw, "preflight_timeout_seconds"),
                actor_timeout_seconds=_positive_integer(limits_raw, "actor_timeout_seconds"),
                judge_timeout_seconds=_positive_integer(limits_raw, "judge_timeout_seconds"),
                maximum_captured_output_bytes=_positive_integer(limits_raw, "maximum_captured_output_bytes"),
            ),
            docker_engine=_string(fixtures_raw, "docker_engine"),
            mockserver=MockServerPin(
                version=_plain_version(mockserver_raw, "version"),
                image=_string(mockserver_raw, "image"),
                digest=mockserver_digest,
                bind=_string(mockserver_raw, "bind"),
                reuse_scope=_string(mockserver_raw, "reuse_scope"),
                ca_scope=_string(mockserver_raw, "ca_scope"),
                maximum_expected_requests=_positive_integer(
                    mockserver_raw, "maximum_expected_requests"
                ),
                bundled_default_ca_sha256=_hex_string(
                    mockserver_raw, "bundled_default_ca_sha256", 64
                ),
                schema_release=_string(schema_raw, "release"),
                schema_source=_string(schema_raw, "source"),
                schema_path=Path(_string(schema_raw, "path")),
                schema_sha256=_hex_string(schema_raw, "sha256", 64),
                reset_per_case=_string_tuple(mockserver_raw, "reset_per_case"),
                passthrough=_boolean(mockserver_raw, "passthrough"),
            ),
            case_isolation=CaseIsolation(
                fresh_worker_projection=_boolean(isolation_raw, "fresh_worker_projection"),
                fresh_home=_boolean(isolation_raw, "fresh_home"),
                fresh_workspace=_boolean(isolation_raw, "fresh_workspace"),
                fresh_codex_home_from_proxy_stubs=_boolean(
                    isolation_raw, "fresh_codex_home_from_proxy_stubs"
                ),
                fresh_tmpdir=_boolean(isolation_raw, "fresh_tmpdir"),
                ephemeral_harness_session=_boolean(isolation_raw, "ephemeral_harness_session"),
                durable_results_mounted_into_actor=_boolean(
                    isolation_raw, "durable_results_mounted_into_actor"
                ),
                writable_filesystem=_string(isolation_raw, "writable_filesystem"),
                maximum_writable_bytes=_positive_integer(
                    isolation_raw, "maximum_writable_bytes"
                ),
                maximum_writable_inodes=_positive_integer(
                    isolation_raw, "maximum_writable_inodes"
                ),
                reset_failure=_string(isolation_raw, "reset_failure"),
            ),
        )
        manifest._validate_policy()
        return manifest

    def _validate_policy(self) -> None:
        if self.schema_version != 1 or self.runtime != "docker-sandboxes":
            raise ManifestError("unsupported evaluation runtime schema or runtime")
        if self.sbx.network_policy.preset != "balanced":
            raise ManifestError("sbx.network_policy.preset must be balanced")
        required_balanced_rules = {
            "default-ai-services",
            "default-package-managers",
            "default-code-and-containers",
            "default-cloud-infrastructure",
            "default-os-packages",
            "default-cert-validation",
        }
        if set(self.sbx.network_policy.required_rule_ids) != required_balanced_rules:
            raise ManifestError("sbx.network_policy must declare every balanced preset rule")
        if self.codex.agent != "codex" or self.codex.allow_login_shell:
            raise ManifestError("codex runtime must use the codex agent with login shells disabled")
        required_flags = {
            "--json",
            "--ephemeral",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        }
        if not required_flags.issubset(self.codex.exec_flags) or "--ignore-user-config" in self.codex.exec_flags:
            raise ManifestError("codex.exec_flags must preserve the pinned isolated JSONL contract")
        if self.codex.fixture_environment_scope != "shell-subprocesses":
            raise ManifestError("fixture environment must be limited to shell subprocesses")
        if self.authentication.mode != "host-proxied-oauth" or self.authentication.copy_host_credentials:
            raise ManifestError("authentication must use host-proxied OAuth without copied credentials")
        if self.workers.cpus <= 0 or not re.fullmatch(r"[1-9][0-9]*[mg]", self.workers.memory):
            raise ManifestError("worker CPU and memory limits must be positive and explicit")
        if self.workers.reuse_scope != "one-cli-invocation":
            raise ManifestError("workers may only be reused for one CLI invocation")
        if not self.workers.separate_actor_and_judge_pools:
            raise ManifestError("actor and judge worker pools must remain separate")
        if self.docker_engine != "sandbox-private" or self.mockserver.passthrough:
            raise ManifestError("fixture networking must use a private engine with passthrough disabled")
        expected_schema_release = f"mockserver-{self.mockserver.version}"
        expected_schema_source = (
            "https://raw.githubusercontent.com/mock-server/mockserver/"
            f"{expected_schema_release}/mockserver-vscode/schemas/"
            "mockserver-expectation.schema.json"
        )
        expected_schema_path = (
            Path("schemas/vendor/mockserver")
            / self.mockserver.version
            / "expectations.schema.json"
        )
        if (
            self.mockserver.image != "mockserver/mockserver"
            or self.mockserver.bind != "microvm-loopback"
            or self.mockserver.reuse_scope != "case"
            or self.mockserver.ca_scope != "case"
            or self.mockserver.maximum_expected_requests != 128
            or self.mockserver.schema_release != expected_schema_release
            or self.mockserver.schema_source != expected_schema_source
            or self.mockserver.schema_path != expected_schema_path
            or self.mockserver.reset_per_case
            != ("expectations", "request_history", "fixture_files")
        ):
            raise ManifestError("mockserver isolation and schema policy cannot be weakened")
        isolation = self.case_isolation
        if not all(
            (
                isolation.fresh_worker_projection,
                isolation.fresh_home,
                isolation.fresh_workspace,
                isolation.fresh_codex_home_from_proxy_stubs,
                isolation.fresh_tmpdir,
                isolation.ephemeral_harness_session,
            )
        ) or isolation.durable_results_mounted_into_actor:
            raise ManifestError("case isolation invariants cannot be weakened")
        if (
            isolation.writable_filesystem != "tmpfs"
            or isolation.maximum_writable_bytes != CASE_TMPFS_SIZE_BYTES
            or isolation.maximum_writable_inodes != CASE_TMPFS_NR_INODES
        ):
            raise ManifestError("case writable filesystem quotas must match the pinned tmpfs")
        if isolation.reset_failure != "fail-case-and-recycle-worker":
            raise ManifestError("reset failures must fail the case and recycle the worker")


@dataclass(frozen=True)
class PreflightReport:
    available: bool
    details: tuple[str, ...]
    failure: str | None = None


@dataclass(frozen=True)
class SandboxWorker:
    id: str
    name: str
    role: WorkerRole
    slot: int
    host_root: Path


@dataclass(frozen=True)
class CaseWorkspace:
    """Fresh actor- or judge-visible directories for one attempted run."""

    case_id: str
    root: Path
    home: Path
    codex_home: Path
    tmpdir: Path
    workspace: Path
    skills: Path
    bootstrap: Path
    user_name: str
    uid: int
    host_staging_root: Path | None = None
    host_export_bridge: Path | None = None
    filesystem_source: str | None = None
    system_var_tmp: Path | None = None
    system_dev_shm: Path | None = None
    system_run_lock: Path | None = None
    system_run_secrets: Path | None = None
    cgroup_path: Path | None = None


@dataclass
class CleanupTarget:
    name: str
    id: str | None
    host_root: Path
    ownership_marker_sha256: str
    create_started: bool = False
    create_process_settled: bool = False
    removal_started: bool = False
    removal_process_settled: bool = False
    removal_issued: bool = False
    sandbox_removed: bool = False
    discard_without_export: bool = False

    @property
    def ownership_marker(self) -> Path:
        return self.host_root / OWNERSHIP_MARKER_FILENAME


@dataclass(frozen=True)
class _OpenedDockerProfileFile:
    name: str
    descriptor: int
    content: bytes
    identity: tuple[int, int]


@contextmanager
def _open_docker_codex_profile(
    codex_home: Path,
) -> Iterator[tuple[int, tuple[_OpenedDockerProfileFile, ...]]]:
    directory_descriptor: int | None = None
    file_descriptors: list[int] = []
    try:
        try:
            observed_directory = os.stat(codex_home, follow_symlinks=False)
            if not stat.S_ISDIR(observed_directory.st_mode):
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state is incomplete"
                )
            directory_descriptor = os.open(
                codex_home,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            opened_directory = os.fstat(directory_descriptor)
        except SandboxRuntimeError:
            raise
        except OSError as error:
            raise SandboxRuntimeError(
                "Docker-generated Codex proxy state is incomplete"
            ) from error
        if (
            not stat.S_ISDIR(opened_directory.st_mode)
            or _stable_profile_metadata(opened_directory)
            != _stable_profile_metadata(observed_directory)
        ):
            raise SandboxRuntimeError(
                "Docker-generated Codex proxy state changed while being read"
            )

        opened_files: list[_OpenedDockerProfileFile] = []
        for name in ("config.toml", "auth.json"):
            try:
                observed = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state is incomplete"
                ) from error
            if not stat.S_ISREG(observed.st_mode):
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state is incomplete"
                )
            if observed.st_size > _MAX_DOCKER_CODEX_PROFILE_BYTES:
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state is unexpectedly large"
                )
            try:
                descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_descriptor,
                )
                file_descriptors.append(descriptor)
                opened = os.fstat(descriptor)
            except OSError as error:
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state changed while being read"
                ) from error
            if (
                not stat.S_ISREG(opened.st_mode)
                or _stable_profile_metadata(opened)
                != _stable_profile_metadata(observed)
            ):
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state changed while being read"
                )
            content = _read_bounded_profile_descriptor(descriptor, opened)
            try:
                current = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state changed while being read"
                ) from error
            if _stable_profile_metadata(current) != _stable_profile_metadata(opened):
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state changed while being read"
                )
            opened_files.append(
                _OpenedDockerProfileFile(
                    name=name,
                    descriptor=descriptor,
                    content=content,
                    identity=(opened.st_dev, opened.st_ino),
                )
            )
        _verify_profile_directory_identity(
            codex_home,
            directory_descriptor,
            (opened_directory.st_dev, opened_directory.st_ino),
            error_message=(
                "Docker-generated Codex proxy state changed while being read"
            ),
        )
        yield directory_descriptor, tuple(opened_files)
    finally:
        for descriptor in reversed(file_descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        if directory_descriptor is not None:
            try:
                os.close(directory_descriptor)
            except OSError:
                pass


def _read_bounded_profile_descriptor(
    descriptor: int,
    expected: os.stat_result,
) -> bytes:
    if (
        not stat.S_ISREG(expected.st_mode)
        or expected.st_size < 0
        or expected.st_size > _MAX_DOCKER_CODEX_PROFILE_BYTES
    ):
        raise SandboxRuntimeError(
            "Docker-generated Codex proxy state is unexpectedly large"
        )
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        remaining = expected.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(
                descriptor,
                min(_PROFILE_READ_CHUNK_BYTES, remaining),
            )
            if not chunk:
                raise SandboxRuntimeError(
                    "Docker-generated Codex proxy state changed while being read"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SandboxRuntimeError(
                "Docker-generated Codex proxy state changed while being read"
            )
        final = os.fstat(descriptor)
    except SandboxRuntimeError:
        raise
    except (OSError, MemoryError, OverflowError) as error:
        raise SandboxRuntimeError(
            "Docker-generated Codex proxy state changed while being read"
        ) from error
    if _stable_profile_metadata(final) != _stable_profile_metadata(expected):
        raise SandboxRuntimeError(
            "Docker-generated Codex proxy state changed while being read"
        )
    try:
        return b"".join(chunks)
    except (MemoryError, OverflowError) as error:
        raise SandboxRuntimeError(
            "Docker-generated Codex proxy state changed while being read"
        ) from error


def _verify_docker_codex_profile_handoff(
    codex_home: Path,
    directory_descriptor: int,
    opened_files: Sequence[_OpenedDockerProfileFile],
) -> None:
    opened_directory = os.fstat(directory_descriptor)
    _verify_profile_directory_identity(
        codex_home,
        directory_descriptor,
        (opened_directory.st_dev, opened_directory.st_ino),
        error_message=(
            "Docker-generated Codex proxy state changed before profile handoff"
        ),
    )
    for opened_file in opened_files:
        try:
            descriptor_metadata = os.fstat(opened_file.descriptor)
            visible_metadata = os.stat(
                opened_file.name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise SandboxRuntimeError(
                "Docker-generated Codex proxy state changed before profile handoff"
            ) from error
        if (
            not stat.S_ISREG(descriptor_metadata.st_mode)
            or not stat.S_ISREG(visible_metadata.st_mode)
            or (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
            != opened_file.identity
            or (visible_metadata.st_dev, visible_metadata.st_ino)
            != opened_file.identity
            or descriptor_metadata.st_size != len(opened_file.content)
            or visible_metadata.st_size != len(opened_file.content)
        ):
            raise SandboxRuntimeError(
                "Docker-generated Codex proxy state changed before profile handoff"
            )
        current_content = _read_bounded_profile_descriptor(
            opened_file.descriptor,
            descriptor_metadata,
        )
        if not hmac.compare_digest(current_content, opened_file.content):
            raise SandboxRuntimeError(
                "Docker-generated Codex proxy state changed before profile handoff"
            )
        try:
            final_descriptor_metadata = os.fstat(opened_file.descriptor)
            final_visible_metadata = os.stat(
                opened_file.name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise SandboxRuntimeError(
                "Docker-generated Codex proxy state changed before profile handoff"
            ) from error
        if (
            (final_descriptor_metadata.st_dev, final_descriptor_metadata.st_ino)
            != opened_file.identity
            or (final_visible_metadata.st_dev, final_visible_metadata.st_ino)
            != opened_file.identity
            or final_descriptor_metadata.st_size != len(opened_file.content)
            or final_visible_metadata.st_size != len(opened_file.content)
        ):
            raise SandboxRuntimeError(
                "Docker-generated Codex proxy state changed before profile handoff"
            )
    _verify_profile_directory_identity(
        codex_home,
        directory_descriptor,
        (opened_directory.st_dev, opened_directory.st_ino),
        error_message=(
            "Docker-generated Codex proxy state changed before profile handoff"
        ),
    )


def _verify_profile_directory_identity(
    codex_home: Path,
    directory_descriptor: int,
    expected_identity: tuple[int, int],
    *,
    error_message: str,
) -> None:
    try:
        opened = os.fstat(directory_descriptor)
        visible = os.stat(codex_home, follow_symlinks=False)
    except OSError as error:
        raise SandboxRuntimeError(error_message) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(visible.st_mode)
        or (opened.st_dev, opened.st_ino) != expected_identity
        or (visible.st_dev, visible.st_ino) != expected_identity
    ):
        raise SandboxRuntimeError(error_message)


def _stable_profile_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


class SandboxRuntime:
    """Own invocation-scoped Docker Sandboxes workers and nothing else."""

    def __init__(
        self,
        *,
        manifest: EvalRuntimeManifest,
        process: ProcessRunner,
        repository_root: Path,
        results_root: Path,
        staging_root: Path,
        invocation_id: str,
        max_concurrency: int,
    ) -> None:
        self.manifest = manifest
        self.process = process
        self.repository_root = repository_root.resolve()
        self.results_root = results_root.resolve()
        self.staging_root = staging_root.resolve()
        self.invocation_id = _safe_identifier(invocation_id)
        if max_concurrency not in range(1, manifest.workers.maximum_concurrency + 1):
            raise SandboxRuntimeError(
                f"max_concurrency must be between 1 and {manifest.workers.maximum_concurrency}"
            )
        self.max_concurrency = max_concurrency
        for root in (self.results_root, self.staging_root):
            if (
                root == self.repository_root
                or root.is_relative_to(self.repository_root)
                or self.repository_root.is_relative_to(root)
            ):
                raise SandboxRuntimeError("result and staging roots must remain outside the repository")
        if self.results_root == self.staging_root or self.results_root.is_relative_to(self.staging_root):
            raise SandboxRuntimeError("durable results must remain outside worker staging roots")
        if self.staging_root.is_relative_to(self.results_root):
            raise SandboxRuntimeError("worker staging roots must remain outside durable results")
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self._workers: dict[tuple[WorkerRole, int], SandboxWorker] = {}
        self._cleanup_targets: dict[str, CleanupTarget] = {}
        self._case_sequences: dict[str, int] = {}
        self._active_cases: dict[str, CaseWorkspace] = {}
        self._proxy_state_digests: dict[str, tuple[str, str]] = {}
        self._mounted_case_filesystems: set[str] = set()
        self._guarded_worker_mounts: set[str] = set()
        self._sealed_skill_catalogs: set[str] = set()
        self._quiesced_cases: set[str] = set()
        self._busy_workers: set[tuple[WorkerRole, int]] = set()
        self._worker_condition = threading.Condition()
        self._closed = False
        self._closing = False
        self._sandbox_cleanup_completed = False

    @property
    def sandbox_cleanup_completed(self) -> bool:
        """Whether every invocation-owned sandbox has verified removal."""
        with self._worker_condition:
            return self._sandbox_cleanup_completed

    def preflight(self) -> PreflightReport:
        """Validate host-side pinned runtime capabilities without exposing secrets."""
        try:
            timeout = self.manifest.limits.preflight_timeout_seconds
            version = self._checked(("sbx", "version"), timeout)
            expected_version = f"v{self.manifest.sbx.version}"
            if expected_version not in version.stdout or self.manifest.sbx.revision not in version.stdout:
                raise SandboxRuntimeError("Docker Sandboxes version or revision does not match the runtime pin")

            diagnose = self._json_command(("sbx", "diagnose", "--output", "json"), timeout)
            summary = _mapping(diagnose.get("summary"), "sbx diagnose summary")
            if summary.get("fail") != 0 or summary.get("skip") != 0:
                raise SandboxRuntimeError("Docker Sandboxes diagnostics did not pass cleanly")
            checks = diagnose.get("checks")
            if not isinstance(checks, list) or not checks:
                raise SandboxRuntimeError("Docker Sandboxes named diagnostics are unavailable")
            names: set[str] = set()
            statuses: list[str] = []
            for check in checks:
                if (
                    not isinstance(check, Mapping)
                    or not isinstance(check.get("name"), str)
                    or not check["name"]
                    or check["name"] in names
                ):
                    raise SandboxRuntimeError(
                        "Docker Sandboxes named diagnostic did not pass"
                    )
                status = check.get("status")
                if status != "pass" and not _is_pinned_binary_update_notice(
                    check,
                    expected_version,
                ):
                    raise SandboxRuntimeError(
                        "Docker Sandboxes named diagnostic did not pass"
                    )
                names.add(check["name"])
                statuses.append(status)
            if (
                summary.get("pass") != statuses.count("pass")
                or summary.get("warn") != statuses.count("warn")
                or len(statuses) != len(checks)
            ):
                raise SandboxRuntimeError(
                    "Docker Sandboxes diagnostic summary does not match named checks"
                )

            secret = self._checked(
                ("sbx", "secret", "ls", "-g", "--service", self.manifest.authentication.service),
                timeout,
            )
            if "(oauth configured)" not in secret.stdout:
                raise SandboxRuntimeError("host-proxied OpenAI OAuth is not configured")

            templates = self._json_command(("sbx", "template", "ls", "--json"), timeout)
            self._verify_template(templates)

            policies = self._json_command(
                ("sbx", "policy", "ls", "--json", "--type", "network"), timeout
            )
            self._verify_network_policy(policies)
            self._probe_results_root()
        except (ManifestError, OSError, SandboxRuntimeError) as error:
            return PreflightReport(available=False, details=(), failure=str(error))
        return PreflightReport(
            available=True,
            details=(
                f"sbx v{self.manifest.sbx.version}",
                f"network policy {self.manifest.sbx.network_policy.preset}",
                "host-proxied OAuth configured",
                "pinned Codex template available",
            ),
        )

    def acquire_worker(self, role: WorkerRole, slot: int = 0) -> SandboxWorker:
        with self._worker_condition:
            if self._closed or self._closing:
                raise SandboxRuntimeError("sandbox runtime is closed")
            if role not in ("actor", "judge"):
                raise SandboxRuntimeError("worker role must be actor or judge")
            if slot not in range(self.max_concurrency):
                raise SandboxRuntimeError("worker slot exceeds configured concurrency")
            key = (role, slot)
            existing = self._workers.get(key)
            if existing is not None:
                return existing

            name = f"ai-skills-{self.invocation_id}-{role}-{slot + 1}"
            if name in self._cleanup_targets:
                raise SandboxRuntimeError("a previous worker with this name is pending verified cleanup")
            if any(item.get("name") == name for item in self._list_sandboxes()):
                raise SandboxRuntimeError(
                    "sandbox worker name already exists and is not owned by this invocation"
                )
            host_root = self.staging_root / name
            host_root.mkdir(parents=True, exist_ok=False)
            marker_content = f"{secrets.token_hex(OWNERSHIP_NONCE_BYTES)}\n".encode("ascii")
            target = CleanupTarget(
                name=name,
                id=None,
                host_root=host_root,
                ownership_marker_sha256=hashlib.sha256(marker_content).hexdigest(),
            )
            self._cleanup_targets[name] = target
            command = (
                "sbx",
                "create",
                "--name",
                name,
                "--cpus",
                str(self.manifest.workers.cpus),
                "--memory",
                self.manifest.workers.memory,
                "--template",
                self.manifest.codex.template,
                self.manifest.codex.agent,
                str(host_root),
            )
            try:
                self._write_ownership_marker(target, marker_content)
                target.create_started = True
                try:
                    create_result = self._checked(
                        command,
                        self.manifest.limits.preflight_timeout_seconds,
                    )
                except BaseException as create_error:
                    create_outcome = process_termination_outcome(create_error)
                    if create_outcome is not None:
                        target.create_process_settled = (
                            create_outcome.fully_terminated_and_reaped
                        )
                        if not create_outcome.process_started:
                            target.create_started = False
                    raise
                else:
                    target.create_process_settled = (
                        create_result.process_outcome.fully_terminated_and_reaped
                    )
                sandbox_id = self._exact_cleanup_identity(target, self._list_sandboxes())
                if sandbox_id is None:
                    raise SandboxRuntimeError(
                        "created sandbox identity could not be reconciled from sbx ls --json"
                    )
            except BaseException as error:
                self._reconcile_failed_create(target, error)
            assert target.id is not None
            worker = SandboxWorker(
                id=target.id,
                name=name,
                role=role,
                slot=slot,
                host_root=host_root,
            )
            self._workers[key] = worker
            return worker

    @contextmanager
    def lease_worker(self, role: WorkerRole) -> Iterator[SandboxWorker]:
        """Lease one role-specific worker under the invocation-wide concurrency cap."""
        if role not in ("actor", "judge"):
            raise SandboxRuntimeError("worker role must be actor or judge")
        reservation: tuple[WorkerRole, int] | None = None
        worker: SandboxWorker | None = None
        try:
            with self._worker_condition:
                while True:
                    if self._closed or self._closing:
                        raise SandboxRuntimeError("sandbox runtime is closed")
                    if len(self._busy_workers) < self.max_concurrency:
                        available = next(
                            (
                                key
                                for key in self._workers
                                if key[0] == role and key not in self._busy_workers
                            ),
                            None,
                        )
                        if available is None:
                            available = next(
                                (
                                    (role, slot)
                                    for slot in range(self.max_concurrency)
                                    if (role, slot) not in self._workers
                                    and (role, slot) not in self._busy_workers
                                ),
                                None,
                            )
                        if available is not None:
                            reservation = available
                            self._busy_workers.add(reservation)
                            worker = self.acquire_worker(*available)
                            break
                    self._worker_condition.wait()
            assert worker is not None and reservation is not None
            worker = self._handoff_leased_worker(worker, reservation)
            yield worker
        finally:
            if reservation is not None:
                try:
                    self._release_worker_reservation(reservation)
                except BaseException:
                    # Set removal is atomic under CPython's GIL and remains the
                    # final fallback if interruption lands inside Condition use.
                    self._busy_workers.discard(reservation)
                    try:
                        with self._worker_condition:
                            self._worker_condition.notify_all()
                    except BaseException:
                        pass
                    raise

    def _release_worker_reservation(
        self,
        reservation: tuple[WorkerRole, int],
    ) -> None:
        with self._worker_condition:
            self._busy_workers.discard(reservation)
            self._worker_condition.notify_all()

    @staticmethod
    def _handoff_leased_worker(
        worker: SandboxWorker,
        reservation: tuple[WorkerRole, int],
    ) -> SandboxWorker:
        if (worker.role, worker.slot) != reservation:
            raise SandboxRuntimeError("acquired worker does not match its lease reservation")
        return worker

    def prepare_case(self, worker: SandboxWorker, case_id: str) -> CaseWorkspace:
        """Erase the mounted projection and create a fresh case-owned layout."""
        self._require_owned_worker(worker)
        try:
            previous = self._active_cases.get(worker.id)
            if previous is not None:
                self._retire_case_identity(worker, previous)
                self._active_cases.pop(worker.id, None)
            safe_case_id = _safe_identifier(case_id)
            case_root = worker.host_root / "case"
            if case_root.exists() or case_root.is_symlink():
                if case_root.is_dir() and not case_root.is_symlink():
                    shutil.rmtree(case_root)
                else:
                    case_root.unlink()
            case_root.mkdir(parents=True)
            directories = {
                "home": case_root / "home",
                "codex_home": case_root / "codex-home",
                "tmpdir": case_root / "tmp",
                "workspace": case_root / "workspace",
                "bootstrap": case_root / "bootstrap",
            }
            system_var_tmp = case_root / ".system-var-tmp"
            system_dev_shm = case_root / ".system-dev-shm"
            system_run_lock = case_root / ".system-run-lock"
            system_run_secrets = case_root / ".system-run-secrets"
            for directory in (
                *directories.values(),
                system_var_tmp,
                system_dev_shm,
                system_run_lock,
                system_run_secrets,
            ):
                directory.mkdir()
            skills = directories["codex_home"] / "skills"
            skills.mkdir()
            (skills / ".system").mkdir()
            for directory in (
                directories["home"] / ".config",
                directories["home"] / ".cache",
                directories["home"] / ".local" / "share",
                directories["home"] / ".local" / "state",
                directories["home"] / ".gnupg",
                directories["tmpdir"] / "runtime",
                directories["tmpdir"] / ".mount-probe",
            ):
                directory.mkdir(parents=True)
            sequence = self._case_sequences.get(worker.id, 0) + 1
            self._case_sequences[worker.id] = sequence
            uid = 20000 + sequence
            user_name = f"ai-eval-{sequence}"
            filesystem_source = (
                f"ai-skills-case-{self.invocation_id}-{worker.role}-"
                f"{worker.slot + 1}-{sequence}"
            )
            case = CaseWorkspace(
                case_id=safe_case_id,
                root=case_root,
                skills=skills,
                user_name=user_name,
                uid=uid,
                host_staging_root=case_root,
                host_export_bridge=Path("/run/ai-skills-evals") / filesystem_source / "host",
                filesystem_source=filesystem_source,
                system_var_tmp=system_var_tmp,
                system_dev_shm=system_dev_shm,
                system_run_lock=system_run_lock,
                system_run_secrets=system_run_secrets,
                cgroup_path=Path("/sys/fs/cgroup/ai-skills-evals")
                / filesystem_source,
                **directories,
            )
            self._prepare_case_identity(worker, case)
            self._active_cases[worker.id] = case
            return case
        except BaseException as error:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"case reset failed and worker cleanup is pending: {cleanup_error}"
                ) from error
            if not isinstance(error, Exception):
                raise
            raise SandboxRuntimeError(f"case reset failed: {error}") from error

    def execute(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        argv: Sequence[str],
        *,
        timeout_seconds: int,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Execute direct arguments in a case and recycle the worker on timeout."""
        self._require_owned_worker(worker)
        if not argv or not all(isinstance(part, str) and part and "\x00" not in part for part in argv):
            raise SandboxRuntimeError("worker command must contain non-empty NUL-free arguments")
        if timeout_seconds <= 0:
            raise SandboxRuntimeError("worker command timeout must be positive")
        if case.root.parent != worker.host_root or not case.root.is_dir():
            raise SandboxRuntimeError("case workspace does not belong to the selected worker")
        rendered_environment = {
            **dict(environment or {}),
        }
        reserved = CASE_OWNED_ENVIRONMENT_NAMES & rendered_environment.keys()
        if reserved:
            raise SandboxRuntimeError("worker environment cannot override reserved case variables")
        rendered_environment.update(
            {
                "HOME": str(case.home),
                "CODEX_HOME": str(case.codex_home),
                "TMPDIR": str(case.tmpdir),
                "USER": case.user_name,
                "LOGNAME": case.user_name,
                "SHELL": "/bin/bash",
                "BASH_ENV": "/dev/null",
                "ENV": "/dev/null",
                "XDG_CONFIG_HOME": str(case.home / ".config"),
                "XDG_CACHE_HOME": str(case.home / ".cache"),
                "XDG_DATA_HOME": str(case.home / ".local" / "share"),
                "XDG_STATE_HOME": str(case.home / ".local" / "state"),
                "XDG_RUNTIME_DIR": str(case.tmpdir / "runtime"),
                "SSH_AUTH_SOCK": "",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GNUPGHOME": str(case.home / ".gnupg"),
                "DOCKER_HOST": "",
            }
        )
        cgroup_path = self._case_cgroup_contract(worker, case)
        command: list[str] = [
            "sbx",
            "exec",
            "--user",
            "root",
            "--workdir",
            str(case.workspace),
        ]
        for name, value in sorted(rendered_environment.items()):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or not isinstance(value, str) or "\x00" in value:
                raise SandboxRuntimeError("worker environment contains an unsafe name or value")
            command.extend(("--env", f"{name}={value}"))
        command.append(worker.name)
        command.extend(
            (
                "python3",
                "-c",
                CASE_CGROUP_EXEC_SCRIPT,
                str(cgroup_path),
                str(case.uid),
            )
        )
        command.extend(argv)
        try:
            self._activate_case_filesystem(worker, case)
            self._require_exact_live_identity(worker.name, worker.id)
            result = self.process.run(tuple(command), timeout_seconds=timeout_seconds)
        except BaseException as error:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"worker command was interrupted and cleanup failed: {cleanup_error}"
                ) from error
            raise
        if result.timed_out:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                result = replace(
                    result,
                    lifecycle_failure=(
                        "timed-out worker cleanup failed: "
                        f"{_safe_diagnostic(str(cleanup_error))}"
                    ),
                )
        return result

    def run_worker_control(
        self,
        worker: SandboxWorker,
        argv: tuple[str, ...],
        *,
        accepted_returncodes: tuple[int, ...] = (0,),
    ) -> CommandResult:
        """Run one checked runner-owned command as root in a private worker."""
        self._require_owned_worker(worker)
        if not argv or not all(
            isinstance(part, str) and part and "\x00" not in part for part in argv
        ):
            raise SandboxRuntimeError("worker control command contains unsafe arguments")
        if not accepted_returncodes or not all(
            isinstance(code, int) and not isinstance(code, bool) for code in accepted_returncodes
        ):
            raise SandboxRuntimeError("worker control command has invalid accepted return codes")
        try:
            result = self._worker_command(
                worker,
                argv,
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
        except BaseException as error:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"worker control command was interrupted and cleanup is pending: {cleanup_error}"
                ) from error
            raise
        if result.timed_out or result.returncode not in accepted_returncodes:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"worker control command failed and cleanup is pending: {cleanup_error}"
                )
            raise SandboxRuntimeError(f"worker control command failed: {argv[0]}")
        return result

    def quiesce_case(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        """Terminate residual case processes before collecting final evidence."""
        self._require_owned_worker(worker)
        if self._active_cases.get(worker.id) is not case:
            raise SandboxRuntimeError("case is not active on the selected worker")
        try:
            self._terminate_and_prove_case_cgroup_empty(worker, case)
            self._clear_case_ipc(worker, case)
            self._deactivate_case_filesystem(worker, case, export_to_host=True)
            self._remove_case_cgroup(worker, case)
            if case.filesystem_source is not None:
                self._quiesced_cases.add(case.filesystem_source)
        except BaseException as error:
            try:
                self.invalidate_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"case quiescence failed and worker cleanup is pending: {cleanup_error}"
                ) from error
            if not isinstance(error, Exception):
                raise
            if isinstance(error, SandboxRuntimeError):
                raise
            raise SandboxRuntimeError(f"case quiescence failed: {error}") from error

    def initialize_codex_home(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        """Copy only Docker's generated provider config and auth placeholder."""
        try:
            self._initialize_codex_home_unchecked(worker, case)
        except Exception as error:
            try:
                self.invalidate_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"Codex proxy setup failed and worker cleanup is pending: {cleanup_error}"
                ) from error
            raise

    def _initialize_codex_home_unchecked(
        self, worker: SandboxWorker, case: CaseWorkspace
    ) -> None:
        result = self._worker_command(
            worker,
            (
                "cp",
                "--",
                "/home/agent/.codex/config.toml",
                "/home/agent/.codex/auth.json",
                str(case.codex_home),
            ),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if result.timed_out or result.returncode != 0:
            raise SandboxRuntimeError("Docker-generated Codex proxy state could not be initialized")
        config_path = case.codex_home / "config.toml"
        auth_path = case.codex_home / "auth.json"
        with _open_docker_codex_profile(case.codex_home) as (
            profile_directory,
            profile_files,
        ):
            profile_by_name = {item.name: item for item in profile_files}
            config_bytes = profile_by_name["config.toml"].content
            auth_bytes = profile_by_name["auth.json"].content
            if not hmac.compare_digest(
                config_bytes,
                _PINNED_DOCKER_CODEX_CONFIG_BYTES,
            ):
                raise SandboxRuntimeError(
                    "Docker-generated Codex config bytes do not match the pinned proxy profile"
                )
            if not hmac.compare_digest(
                auth_bytes,
                _PINNED_DOCKER_CODEX_AUTH_BYTES,
            ):
                raise SandboxRuntimeError(
                    "Docker-generated auth placeholder bytes do not match the pinned proxy profile"
                )
            config = config_bytes.decode("utf-8")
            auth = auth_bytes.decode("utf-8")
            try:
                config_payload = tomllib.loads(config)
            except tomllib.TOMLDecodeError as error:
                raise SandboxRuntimeError(
                    "Docker-generated Codex config is not valid TOML"
                ) from error
            if not _matches_exact_shape(
                config_payload,
                _EXPECTED_DOCKER_CODEX_CONFIG_SHAPE,
            ):
                raise SandboxRuntimeError(
                    "Docker-generated Codex config does not match the pinned proxy profile"
                )
            try:
                auth_payload = json.loads(
                    auth,
                    object_pairs_hook=_unique_json_object,
                )
            except (json.JSONDecodeError, ValueError) as error:
                raise SandboxRuntimeError(
                    "Docker-generated auth placeholder is not valid JSON"
                ) from error
            if not _matches_exact_shape(
                auth_payload,
                _EXPECTED_DOCKER_CODEX_AUTH_SHAPE,
            ):
                raise SandboxRuntimeError(
                    "Docker-generated auth placeholder does not match the pinned proxy profile"
                )
            config_digest = hashlib.sha256(config_bytes).hexdigest()
            auth_digest = hashlib.sha256(auth_bytes).hexdigest()
            current_digests = (config_digest, auth_digest)
            baseline = self._proxy_state_digests.get(worker.id)
            if baseline is not None and baseline != current_digests:
                raise SandboxRuntimeError(
                    "immutable Docker-generated proxy state changed between cases"
                )
            self._admin_checked(
                worker,
                (
                    "chown",
                    f"{case.uid}:{case.uid}",
                    str(config_path),
                    str(auth_path),
                ),
            )
            self._admin_checked(
                worker,
                ("chmod", "0600", str(config_path), str(auth_path)),
            )
            _verify_docker_codex_profile_handoff(
                case.codex_home,
                profile_directory,
                profile_files,
            )
            self._proxy_state_digests.setdefault(worker.id, current_digests)

    def seal_skill_catalog(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        """Mark a fully staged catalog for sealing in the final case filesystem."""
        self._require_owned_worker(worker)
        if self._active_cases.get(worker.id) != case:
            raise SandboxRuntimeError("skill catalog belongs to an inactive case")
        filesystem_source = case.filesystem_source
        if filesystem_source is None:
            raise SandboxRuntimeError("skill catalog filesystem identity is incomplete")
        self._sealed_skill_catalogs.add(filesystem_source)

    def _activate_case_filesystem(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        """Seed and verify the aggregate byte- and inode-bounded case tmpfs."""
        self._require_owned_worker(worker)
        if self._active_cases.get(worker.id) is not case:
            raise SandboxRuntimeError("case filesystem belongs to an inactive case")
        contract = self._case_filesystem_contract(worker, case)
        if worker.id in self._mounted_case_filesystems:
            self._protect_worker_host_mount(worker)
            self._verify_case_filesystem(worker, case)
            self._verify_case_privilege_boundaries(worker, case)
            self._verify_worker_and_catalog_boundaries(worker, case)
            return

        bridge_mount, filesystem_source, system_mounts = contract
        bridge_root = bridge_mount.parent
        bridge_base = bridge_root.parent
        self._admin_checked(worker, ("mkdir", "--parents", str(bridge_mount)))
        self._admin_checked(
            worker,
            ("chown", "root:root", str(bridge_base), str(bridge_root)),
        )
        self._admin_checked(worker, ("chmod", "0700", str(bridge_base), str(bridge_root)))
        self._admin_checked(worker, ("mount", "--bind", str(case.root), str(bridge_mount)))
        self._protect_worker_host_mount(worker)
        isolation = self.manifest.case_isolation
        self._admin_checked(
            worker,
            (
                "mount",
                "-t",
                isolation.writable_filesystem,
                "-o",
                (
                    "rw,nosuid,nodev,"
                    f"size={isolation.maximum_writable_bytes},"
                    f"nr_inodes={isolation.maximum_writable_inodes},mode=0555"
                ),
                filesystem_source,
                str(case.root),
            ),
        )
        self._admin_checked(
            worker,
            (
                "cp",
                "--archive",
                "--one-file-system",
                "--",
                f"{bridge_mount}/.",
                f"{case.root}/",
            ),
        )
        self._configure_case_writable_permissions(worker, case)
        if filesystem_source in self._sealed_skill_catalogs:
            self._apply_sealed_skill_catalog(worker, case)
        self._admin_checked(worker, ("chown", "root:root", str(case.root)))
        self._admin_checked(worker, ("chmod", "0555", str(case.root)))
        self._admin_checked(worker, ("mkdir", "--parents", "/run/lock", "/run/secrets"))
        for source, target in system_mounts:
            self._admin_checked(worker, ("mount", "--bind", str(source), target))
        self._verify_case_filesystem(worker, case)
        self._verify_case_privilege_boundaries(worker, case)
        self._case_user_checked(
            worker,
            case,
            ("test", "!", "-w", str(case.root)),
            "case user can mutate the case tmpfs root",
        )
        for writable_path in (
            case.home,
            case.codex_home,
            case.tmpdir,
            case.workspace,
            case.bootstrap,
            *(Path(target) for _, target in system_mounts),
        ):
            self._case_user_checked(
                worker,
                case,
                ("test", "-w", str(writable_path)),
                "case tmpfs does not cover a required writable path",
            )
        self._case_user_checked(
            worker,
            case,
            ("test", "!", "-x", str(bridge_root)),
            "case user can traverse the host export bridge",
        )
        self._verify_worker_and_catalog_boundaries(worker, case)
        self._mounted_case_filesystems.add(worker.id)

    def _protect_worker_host_mount(self, worker: SandboxWorker) -> None:
        result = self._worker_command(
            worker,
            (
                "python3",
                "-c",
                WORKER_MOUNT_PROTECT_SCRIPT,
                str(worker.host_root),
            ),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if (
            result.timed_out
            or result.returncode != 0
            or result.stdout.strip()
            or result.stderr.strip()
            or result.stdout_truncated
            or result.stderr_truncated
        ):
            raise SandboxRuntimeError("worker host mount could not be protected read-only")
        self._guarded_worker_mounts.add(worker.id)

    def _apply_sealed_skill_catalog(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        system_skills = case.skills / ".system"
        self._admin_checked(worker, ("chown", "-R", "root:root", str(case.skills)))
        self._admin_checked(worker, ("chmod", "-R", "u=rwX,go=rX", str(case.skills)))
        if worker.role == "judge":
            self._admin_checked(
                worker,
                ("chmod", "0555", str(case.skills), str(system_skills)),
            )
        else:
            self._admin_checked(worker, ("chmod", "1777", str(case.skills)))
            self._admin_checked(
                worker,
                ("chown", "-R", f"{case.uid}:{case.uid}", str(system_skills)),
            )
            self._admin_checked(worker, ("chmod", "0700", str(system_skills)))
        self._admin_checked(worker, ("chown", "root:root", str(case.codex_home)))
        self._admin_checked(worker, ("chmod", "1777", str(case.codex_home)))

    def _verify_worker_and_catalog_boundaries(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        self._case_user_checked(
            worker,
            case,
            (
                "python3",
                "-c",
                DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT,
                str(worker.host_root / ".worker-write-probe"),
            ),
            "case user can mutate the worker mount root",
        )
        self._case_user_checked(
            worker,
            case,
            (
                "python3",
                "-c",
                ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
                "/",
                "/proc/self/mountinfo",
                str(case.root),
                "/tmp",
                "/var/tmp",
                "/dev/shm",
                "/run/lock",
                "/run/secrets",
            ),
            "root filesystem exposes writable state outside the case tmpfs",
        )
        if case.filesystem_source not in self._sealed_skill_catalogs:
            return
        if worker.role == "judge":
            for parent in (case.skills, case.skills / ".system"):
                self._case_user_checked(
                    worker,
                    case,
                    (
                        "python3",
                        "-c",
                        DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT,
                        str(parent / ".judge-write-probe"),
                    ),
                    "judge skill catalog is writable",
                )
        else:
            self._case_user_checked(
                worker,
                case,
                (
                    "python3",
                    "-c",
                    PUBLIC_SKILL_CATALOG_PROBE_SCRIPT,
                    str(case.skills),
                ),
                "public skill catalog permissions do not isolate Codex system skills",
            )
        for source, target, failure in (
            (
                case.skills,
                case.codex_home / ".skills-rename-probe",
                "case user can replace the projected skill catalog",
            ),
            (
                case.codex_home,
                case.root / ".codex-home-rename-probe",
                "case user can replace the Codex home containing the skill catalog",
            ),
            (
                case.root,
                worker.host_root / ".case-rename-probe",
                "case user can replace the case root containing the skill catalog",
            ),
        ):
            self._case_user_checked(
                worker,
                case,
                (
                    "python3",
                    "-c",
                    CATALOG_RENAME_PROBE_SCRIPT,
                    str(source),
                    str(target),
                ),
                failure,
            )

    def _verify_case_filesystem(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        _, filesystem_source, _ = self._case_filesystem_contract(worker, case)
        isolation = self.manifest.case_isolation
        covered_paths = (
            case.home,
            case.codex_home,
            case.tmpdir,
            case.workspace,
            case.bootstrap,
            case.system_var_tmp,
            case.system_dev_shm,
            case.system_run_lock,
            case.system_run_secrets,
        )
        if any(path is None for path in covered_paths):
            raise SandboxRuntimeError("case filesystem paths are incomplete")
        self._admin_checked(
            worker,
            (
                "python3",
                "-c",
                CASE_FILESYSTEM_PROBE_SCRIPT,
                str(case.root),
                filesystem_source,
                str(isolation.maximum_writable_bytes),
                str(isolation.maximum_writable_inodes),
                *(str(path) for path in covered_paths),
            ),
        )

    def _deactivate_case_filesystem(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        *,
        export_to_host: bool,
    ) -> None:
        if worker.id not in self._mounted_case_filesystems:
            return
        bridge_mount, _, _ = self._case_filesystem_contract(worker, case)
        if export_to_host:
            self._verify_case_filesystem(worker, case)
            self._admin_checked(
                worker,
                ("chmod", "-R", "u+rwX", str(bridge_mount)),
            )
            self._admin_checked(
                worker,
                (
                    "find",
                    str(bridge_mount),
                    "-mindepth",
                    "1",
                    "-maxdepth",
                    "1",
                    "-exec",
                    "rm",
                    "-rf",
                    "--",
                    "{}",
                    "+",
                ),
            )
            self._admin_checked(
                worker,
                (
                    "cp",
                    "--archive",
                    "--one-file-system",
                    "--",
                    f"{case.root}/.",
                    f"{bridge_mount}/",
                ),
            )
            self._admin_checked(worker, ("sync", "-f", str(bridge_mount)))
        self._cleanup_case_filesystem_mounts(worker.name, worker.id, case)
        self._mounted_case_filesystems.discard(worker.id)

    def _cleanup_case_filesystem_mounts(
        self,
        sandbox_name: str,
        worker_id: str,
        case: CaseWorkspace,
    ) -> None:
        bridge_mount, filesystem_source, system_mounts = self._case_filesystem_contract(
            None,
            case,
        )
        cleanup_mount_contract = tuple(
            item
            for source, target in system_mounts
            for item in (
                target,
                f"/{source.relative_to(case.root).as_posix()}",
            )
        )
        result = self._worker_command_by_name(
            sandbox_name,
            worker_id,
            (
                "python3",
                "-c",
                CASE_FILESYSTEM_CLEANUP_SCRIPT,
                filesystem_source,
                str(case.root),
                str(bridge_mount),
                *cleanup_mount_contract,
            ),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if result.timed_out or result.returncode != 0:
            raise SandboxRuntimeError("case filesystem mounts could not be cleared")
        if worker_id in self._guarded_worker_mounts:
            mount_restore = self._worker_command_by_name(
                sandbox_name,
                worker_id,
                (
                    "python3",
                    "-c",
                    WORKER_MOUNT_RESTORE_SCRIPT,
                    str(case.root.parent),
                ),
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
            if (
                mount_restore.timed_out
                or mount_restore.returncode != 0
                or mount_restore.stdout.strip()
                or mount_restore.stderr.strip()
                or mount_restore.stdout_truncated
                or mount_restore.stderr_truncated
            ):
                raise SandboxRuntimeError("worker host mount could not be restored read-write")
        staging_tree_restore = self._worker_command_by_name(
            sandbox_name,
            worker_id,
            ("chmod", "-R", "u+rwX", str(case.root)),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if staging_tree_restore.timed_out or staging_tree_restore.returncode != 0:
            raise SandboxRuntimeError("case host staging tree could not be reopened for reset")
        restore = self._worker_command_by_name(
            sandbox_name,
            worker_id,
            ("chmod", "0700", str(case.root)),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if restore.timed_out or restore.returncode != 0:
            raise SandboxRuntimeError("case host staging permissions could not be restored")
        verification = self._worker_command_by_name(
            sandbox_name,
            worker_id,
            ("stat", "--format=%a", str(case.root)),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if (
            verification.timed_out
            or verification.returncode != 0
            or verification.stdout.strip() != "700"
            or verification.stderr.strip()
            or verification.stdout_truncated
            or verification.stderr_truncated
        ):
            raise SandboxRuntimeError("case host staging permissions could not be verified")

    @staticmethod
    def _case_filesystem_contract(
        worker: SandboxWorker | None,
        case: CaseWorkspace,
    ) -> tuple[Path, str, tuple[tuple[Path, str], ...]]:
        bridge_mount = case.host_export_bridge
        filesystem_source = case.filesystem_source
        system_paths = (
            (case.tmpdir, "/tmp"),
            (case.system_var_tmp, "/var/tmp"),
            (case.system_dev_shm, "/dev/shm"),
            (case.system_run_lock, "/run/lock"),
            (case.system_run_secrets, "/run/secrets"),
        )
        if (
            case.host_staging_root != case.root
            or bridge_mount is None
            or filesystem_source is None
            or re.fullmatch(r"[a-zA-Z0-9.+-]+", filesystem_source) is None
            or any(source is None for source, _ in system_paths)
        ):
            raise SandboxRuntimeError("case filesystem contract is incomplete")
        assert all(source is not None for source, _ in system_paths)
        rendered_system_paths = tuple(
            (source, target) for source, target in system_paths if source is not None
        )
        if any(source.parent != case.root for source, _ in rendered_system_paths):
            raise SandboxRuntimeError("case scratch path escapes the bounded filesystem")
        expected_bridge = Path("/run/ai-skills-evals") / filesystem_source / "host"
        if bridge_mount != expected_bridge:
            raise SandboxRuntimeError("case host bridge escapes the selected worker")
        return bridge_mount, filesystem_source, rendered_system_paths

    def close(self) -> None:
        close_claimed = False
        terminal_cleanup = False
        try:
            with self._worker_condition:
                if self._closed:
                    return
                if self._closing:
                    raise SandboxRuntimeError(
                        "sandbox runtime cleanup is already in progress"
                    )
                if self._busy_workers:
                    raise SandboxRuntimeError(
                        "cannot close the sandbox runtime while workers are leased"
                    )
                # Mark the local guard first so every interruption after the
                # shared claim is covered by the outer finally.
                close_claimed = True
                self._closing = True
                self._sandbox_cleanup_completed = False
            targets = tuple(self._cleanup_targets.values())
            failures: dict[str, list[BaseException]] = {}
            interruption: BaseException | None = None
            for target in targets:
                try:
                    self._remove_cleanup_target(target)
                except BaseException as error:
                    failures.setdefault(target.name, []).append(error)
                    if not isinstance(error, Exception) and interruption is None:
                        interruption = error

            for target in tuple(self._cleanup_targets.values()):
                if target.sandbox_removed:
                    continue
                try:
                    self._reconcile_cleanup_target(target)
                except BaseException as error:
                    failures.setdefault(target.name, []).append(error)
                    if not isinstance(error, Exception) and interruption is None:
                        interruption = error

            pending = tuple(self._cleanup_targets.values())
            if pending:
                diagnostic = _cleanup_failure_diagnostic(pending, failures)
                if interruption is not None:
                    interruption.add_note(diagnostic)
                    raise interruption
                raise SandboxRuntimeError(diagnostic)
            self._clear_terminal_runtime_state()
            with self._worker_condition:
                self._closed = True
                self._sandbox_cleanup_completed = True
                terminal_cleanup = True
            if interruption is not None:
                raise interruption
        finally:
            if close_claimed:
                if not terminal_cleanup:
                    self._closed = False
                    self._sandbox_cleanup_completed = False
                self._closing = False
                with self._worker_condition:
                    self._worker_condition.notify_all()

    def _clear_terminal_runtime_state(self) -> None:
        self._workers.clear()
        self._cleanup_targets.clear()
        self._active_cases.clear()
        self._proxy_state_digests.clear()
        self._mounted_case_filesystems.clear()
        self._guarded_worker_mounts.clear()
        self._sealed_skill_catalogs.clear()
        self._quiesced_cases.clear()

    def _discard_worker(self, worker: SandboxWorker) -> None:
        self._require_owned_worker(worker)
        target = self._cleanup_targets[worker.name]
        self._quarantine_cleanup_target(target)
        self._remove_cleanup_target(target)

    def invalidate_worker(self, worker: SandboxWorker) -> None:
        """Quarantine and remove a worker whose case setup cannot be trusted."""
        if self._workers.get((worker.role, worker.slot)) is worker:
            self._discard_worker(worker)

    def _remove_cleanup_target(self, target: CleanupTarget) -> None:
        if target.create_started and not target.create_process_settled:
            self._record_exact_cleanup_identity(target)
            raise SandboxRuntimeError(
                "sandbox create process termination is unproven; exact cleanup target, "
                "ownership marker, and staging are retained"
            )
        self._require_removal_process_settled(target)
        if not target.sandbox_removed:
            sandbox_id = self._record_exact_cleanup_identity(target)
            if sandbox_id is None:
                if target.id is None and target.create_started:
                    raise SandboxRuntimeError(
                        "sandbox create operation has no authoritative completion or "
                        "cancellation; exact cleanup target, ownership marker, and "
                        "staging are retained"
                    )
                target.sandbox_removed = True
                self._forget_worker_state(target)
        if not target.sandbox_removed and not target.removal_issued:
            assert target.id is not None
            if not target.discard_without_export:
                self._purge_cleanup_target_host_root(target)
            try:
                self._issue_cleanup_removal(target)
            except BaseException:
                self._quarantine_cleanup_target(target)
                raise
        if not target.sandbox_removed:
            assert target.id is not None
            self._require_cleanup_target_absent(
                target,
                "worker cleanup could not be verified",
            )
            target.sandbox_removed = True
            self._forget_worker_state(target)
        self._remove_host_cleanup_target(target)

    def _reconcile_cleanup_target(self, target: CleanupTarget) -> None:
        """Retry one pending worker using only its exact recorded identity."""
        if target.create_started and not target.create_process_settled:
            self._record_exact_cleanup_identity(target)
            raise SandboxRuntimeError(
                "sandbox create process termination is unproven; exact cleanup target, "
                "ownership marker, and staging are retained"
            )
        self._require_removal_process_settled(target)
        sandbox_id = self._record_exact_cleanup_identity(target)
        if sandbox_id is None:
            if target.id is None:
                if target.create_started:
                    raise SandboxRuntimeError(
                        "sandbox create operation has no authoritative completion or "
                        "cancellation; exact cleanup target, ownership marker, and "
                        "staging are retained"
                    )
            target.sandbox_removed = True
            self._forget_worker_state(target)
            self._remove_host_cleanup_target(target)
            return

        if not target.discard_without_export:
            self._purge_cleanup_target_host_root(target)
        try:
            self._issue_cleanup_removal(target)
        except BaseException:
            self._quarantine_cleanup_target(target)
            raise
        self._require_cleanup_target_absent(
            target,
            "worker cleanup reconciliation could not verify absence",
        )
        target.sandbox_removed = True
        self._forget_worker_state(target)
        self._remove_host_cleanup_target(target)

    @staticmethod
    def _require_removal_process_settled(target: CleanupTarget) -> None:
        if target.removal_started and not target.removal_process_settled:
            raise SandboxRuntimeError(
                "sandbox removal process termination is unproven; exact cleanup "
                "target, ownership marker, and staging are retained"
            )

    def _issue_cleanup_removal(
        self,
        target: CleanupTarget,
    ) -> None:
        if target.id is None:
            raise SandboxRuntimeError("sandbox removal requires a verified identity")
        if self._record_exact_cleanup_identity(target) is None:
            target.sandbox_removed = True
            self._forget_worker_state(target)
            return
        target.removal_started = True
        target.removal_process_settled = False
        try:
            result = self._checked(
                ("sbx", "rm", "--force", target.name),
                self.manifest.limits.preflight_timeout_seconds,
            )
        except BaseException as error:
            outcome = process_termination_outcome(error)
            if outcome is not None:
                target.removal_started = outcome.process_started
                target.removal_process_settled = (
                    outcome.fully_terminated_and_reaped
                )
            raise
        target.removal_process_settled = (
            result.process_outcome.fully_terminated_and_reaped
        )
        if not target.removal_process_settled:
            raise SandboxRuntimeError(
                "sandbox removal process termination is unproven"
            )
        target.removal_issued = True

    def _exact_cleanup_identity(
        self,
        target: CleanupTarget,
        sandboxes: Sequence[Mapping[str, object]],
    ) -> str | None:
        name_matches = [item for item in sandboxes if item.get("name") == target.name]
        if target.id is None:
            if not name_matches:
                return None
            if len(name_matches) != 1 or not isinstance(name_matches[0].get("id"), str):
                raise SandboxRuntimeError("pending worker cleanup identity remains ambiguous")
            candidate_id = name_matches[0]["id"]
            self._prove_candidate_ownership(target)
            target.id = candidate_id
            return target.id

        id_matches = [item for item in sandboxes if item.get("id") == target.id]
        if not id_matches and not name_matches:
            return None
        if (
            len(id_matches) != 1
            or len(name_matches) != 1
            or id_matches[0].get("name") != target.name
            or name_matches[0].get("id") != target.id
        ):
            raise SandboxRuntimeError("pending worker cleanup identity no longer matches")
        return target.id

    def _record_exact_cleanup_identity(self, target: CleanupTarget) -> str | None:
        return self._exact_cleanup_identity(target, self._list_sandboxes())

    def _require_cleanup_target_absent(
        self,
        target: CleanupTarget,
        message: str,
    ) -> None:
        try:
            remaining_id = self._exact_cleanup_identity(
                target,
                self._list_sandboxes(),
            )
        except BaseException:
            self._quarantine_cleanup_target(target)
            raise
        if remaining_id is not None:
            self._quarantine_cleanup_target(target)
            raise SandboxRuntimeError(message)

    def _prove_candidate_ownership(
        self,
        target: CleanupTarget,
    ) -> None:
        local_digest = self._read_local_ownership_marker_digest(target)
        if not hmac.compare_digest(local_digest, target.ownership_marker_sha256):
            raise SandboxRuntimeError(
                "same-named sandbox candidate did not prove invocation ownership"
            )
        result = self.process.run(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                target.name,
                "python3",
                "-c",
                OWNERSHIP_MARKER_PROBE_SCRIPT,
                str(target.ownership_marker),
            ),
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        candidate_digest = result.stdout.strip()
        if (
            result.timed_out
            or result.returncode != 0
            or result.stdout_truncated
            or result.stderr_truncated
            or re.fullmatch(r"[0-9a-f]{64}", candidate_digest) is None
            or not hmac.compare_digest(candidate_digest, target.ownership_marker_sha256)
        ):
            raise SandboxRuntimeError(
                "same-named sandbox candidate did not prove invocation ownership"
            )

    @staticmethod
    def _write_ownership_marker(target: CleanupTarget, content: bytes) -> None:
        descriptor: int | None = None
        try:
            descriptor = os.open(
                target.ownership_marker,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            remaining = memoryview(content)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("ownership marker write made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @staticmethod
    def _read_local_ownership_marker_digest(target: CleanupTarget) -> str:
        descriptor: int | None = None
        try:
            descriptor = os.open(target.ownership_marker, os.O_RDONLY | os.O_NOFOLLOW)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > 256:
                raise OSError("ownership marker is not a bounded regular file")
            content = os.read(descriptor, before.st_size + 1)
            after = os.fstat(descriptor)
            if (
                len(content) != before.st_size
                or before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise OSError("ownership marker changed while being read")
            return hashlib.sha256(content).hexdigest()
        except OSError as error:
            raise SandboxRuntimeError("sandbox ownership marker is unavailable") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _purge_cleanup_target_host_root(self, target: CleanupTarget) -> None:
        if target.id is None:
            raise SandboxRuntimeError("worker host-root purge requires proven sandbox ownership")
        self._require_exact_live_identity(target.name, target.id)
        try:
            active_case = self._active_cases.get(target.id)
            if active_case is not None:
                quiesced = active_case.filesystem_source in self._quiesced_cases
                if not quiesced:
                    self._terminate_and_prove_case_cgroup_empty_by_name(
                        target.name,
                        target.id,
                        active_case,
                    )
                    self._clear_case_ipc_by_name(target.name, target.id, active_case)
                    self._cleanup_case_filesystem_mounts(
                        target.name,
                        target.id,
                        active_case,
                    )
                    self._mounted_case_filesystems.discard(target.id)
                    self._remove_case_cgroup_by_name(
                        target.name,
                        target.id,
                        active_case,
                    )
            purge = self._worker_command_by_name(
                target.name,
                target.id,
                (
                    "find",
                    str(target.host_root),
                    "-mindepth",
                    "1",
                    "-maxdepth",
                    "1",
                    "-exec",
                    "rm",
                    "-rf",
                    "--",
                    "{}",
                    "+",
                ),
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
            if purge.timed_out or purge.returncode != 0:
                diagnostic = _safe_diagnostic(
                    purge.stderr.strip()
                    or purge.stdout.strip()
                    or ("command timed out" if purge.timed_out else "no diagnostic")
                )
                raise SandboxRuntimeError(
                    f"worker host-root purge failed: {diagnostic}"
                )
        except BaseException:
            self._quarantine_cleanup_target(target)
            raise

    def _quarantine_cleanup_target(self, target: CleanupTarget) -> None:
        target.discard_without_export = True
        for key, worker in tuple(self._workers.items()):
            if worker.name != target.name:
                continue
            self._workers.pop(key, None)
            self._proxy_state_digests.pop(worker.id, None)

    def _remove_host_cleanup_target(self, target: CleanupTarget) -> None:
        if not target.sandbox_removed:
            raise SandboxRuntimeError("worker host staging cleanup requires verified sandbox removal")
        if target.host_root.exists():
            _grant_owner_directory_removal_access(target.host_root)
            shutil.rmtree(target.host_root)
        if target.host_root.exists():
            raise SandboxRuntimeError("worker host staging cleanup could not be verified")
        self._cleanup_targets.pop(target.name, None)

    def _forget_worker_state(self, target: CleanupTarget) -> None:
        for key, worker in tuple(self._workers.items()):
            if worker.name != target.name:
                continue
            self._workers.pop(key, None)
            active_case = self._active_cases.pop(worker.id, None)
            if active_case is not None and active_case.filesystem_source is not None:
                self._sealed_skill_catalogs.discard(active_case.filesystem_source)
                self._quiesced_cases.discard(active_case.filesystem_source)
            self._proxy_state_digests.pop(worker.id, None)
            self._mounted_case_filesystems.discard(worker.id)
            self._guarded_worker_mounts.discard(worker.id)
        if target.id is not None:
            active_case = self._active_cases.pop(target.id, None)
            if active_case is not None and active_case.filesystem_source is not None:
                self._sealed_skill_catalogs.discard(active_case.filesystem_source)
                self._quiesced_cases.discard(active_case.filesystem_source)
            self._proxy_state_digests.pop(target.id, None)
            self._mounted_case_filesystems.discard(target.id)
            self._guarded_worker_mounts.discard(target.id)

    def _reconcile_failed_create(
        self,
        target: CleanupTarget,
        error: BaseException,
    ) -> None:
        if not target.create_started:
            target.sandbox_removed = True
            try:
                self._remove_host_cleanup_target(target)
            except BaseException as cleanup_error:
                if not isinstance(cleanup_error, Exception):
                    raise
                raise SandboxRuntimeError(
                    "sandbox setup failed before creation and host cleanup is pending: "
                    f"{_safe_diagnostic(str(cleanup_error))}"
                ) from error
            raise error

        try:
            sandbox_id = self._exact_cleanup_identity(target, self._list_sandboxes())
        except BaseException as reconciliation_error:
            if not isinstance(reconciliation_error, Exception):
                raise
            raise SandboxRuntimeError(
                "sandbox creation failed and unresolved ownership cleanup is pending: "
                f"{_safe_diagnostic(str(reconciliation_error))}"
            ) from error
        if not target.create_process_settled:
            raise SandboxRuntimeError(
                "sandbox creation failed before its process was definitively terminated "
                "and reaped; exact cleanup target, ownership marker, and staging are retained"
            ) from error
        if sandbox_id is None:
            raise SandboxRuntimeError(
                "sandbox creation failed because no authoritative operation completion or "
                "cancellation is available; exact cleanup target, ownership marker, and "
                "staging are retained"
            ) from error

        try:
            self._remove_cleanup_target(target)
        except BaseException as cleanup_error:
            if not isinstance(cleanup_error, Exception):
                raise
            raise SandboxRuntimeError(
                "sandbox creation failed and verified cleanup is pending: "
                f"{_safe_diagnostic(str(cleanup_error))}"
            ) from error
        raise error

    def _require_owned_worker(self, worker: SandboxWorker) -> None:
        if self._workers.get((worker.role, worker.slot)) is not worker:
            raise SandboxRuntimeError("worker is not owned by this invocation")

    def _require_exact_live_identity(self, sandbox_name: str, sandbox_id: str) -> None:
        sandboxes = self._list_sandboxes()
        name_matches = [item for item in sandboxes if item.get("name") == sandbox_name]
        id_matches = [item for item in sandboxes if item.get("id") == sandbox_id]
        if (
            len(name_matches) != 1
            or len(id_matches) != 1
            or name_matches[0].get("id") != sandbox_id
            or id_matches[0].get("name") != sandbox_name
        ):
            raise SandboxRuntimeError("sandbox identity no longer matches")

    def _prepare_case_identity(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self._admin_checked(
            worker,
            ("chown", "root:root", "/var/lib/pebble/default"),
        )
        self._admin_checked(
            worker,
            ("chmod", "0755", "/var/lib/pebble/default"),
        )
        self._admin_checked(
            worker,
            ("chown", "root:root", "/opt/containerd", "/run/containerd"),
        )
        self._admin_checked(
            worker,
            ("chmod", "0700", "/opt/containerd", "/run/containerd"),
        )
        self._admin_checked(worker, ("chmod", "0700", "/home/agent"))
        self._admin_checked(worker, ("chmod", "0700", "/home/agent/.codex"))
        self._admin_checked(
            worker,
            ("chmod", "0600", "/home/agent/.codex/config.toml", "/home/agent/.codex/auth.json"),
        )
        self._admin_checked(
            worker,
            (
                "useradd",
                "--no-create-home",
                "--home-dir",
                str(case.home),
                "--shell",
                "/bin/bash",
                "--user-group",
                "--uid",
                str(case.uid),
                case.user_name,
            ),
        )
        self._setup_case_cgroup(worker, case)
        self._configure_case_writable_permissions(worker, case)
        self._lock_down_case_identity(worker, case)

    def _configure_case_writable_permissions(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        self._admin_checked(
            worker,
            ("chown", "-R", f"{case.uid}:{case.uid}", str(case.root)),
        )
        scratch_paths = (
            case.tmpdir,
            case.system_var_tmp,
            case.system_dev_shm,
            case.system_run_lock,
            case.system_run_secrets,
        )
        if any(path is None for path in scratch_paths):
            raise SandboxRuntimeError("case scratch paths are incomplete")
        self._admin_checked(
            worker,
            ("chown", "root:root", *(str(path) for path in scratch_paths)),
        )
        self._admin_checked(
            worker,
            ("chmod", "1777", *(str(path) for path in scratch_paths)),
        )
        self._admin_checked(
            worker,
            ("chmod", "0700", str(case.tmpdir / "runtime")),
        )

    def _lock_down_case_identity(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        self._lock_down_case_privileges(worker)
        self._verify_case_privilege_boundaries(worker, case)
        self._case_user_checked(
            worker,
            case,
            ("test", "!", "-r", "/var/run/docker.sock"),
            "case user can read the sandbox-private Docker socket",
        )
        self._case_user_checked(
            worker,
            case,
            ("test", "!", "-w", "/var/run/docker.sock"),
            "case user can write the sandbox-private Docker socket",
        )
        self._case_user_checked(
            worker,
            case,
            ("test", "!", "-r", "/home/agent/.codex/auth.json"),
            "case user can read the immutable proxy source",
        )

    def _lock_down_case_privileges(self, worker: SandboxWorker) -> None:
        self._admin_checked(
            worker,
            ("python3", "-c", CASE_PRIVILEGE_LOCKDOWN_SCRIPT),
        )

    def _verify_case_privilege_boundaries(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        self._case_user_checked(
            worker,
            case,
            (
                "python3",
                "-c",
                CASE_PRIVILEGE_PROBE_SCRIPT,
                str(case.tmpdir / ".mount-probe"),
            ),
            "case UID can create user namespaces, FUSE state, or mounts",
        )

    def _retire_case_identity(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        quiesced = case.filesystem_source in self._quiesced_cases
        if not quiesced:
            self._terminate_and_prove_case_cgroup_empty(worker, case)
            self._clear_case_ipc(worker, case)
            self._deactivate_case_filesystem(worker, case, export_to_host=False)
        self._admin_checked(worker, ("userdel", case.user_name), accepted=(0, 6))
        self._admin_checked(worker, ("groupdel", case.user_name), accepted=(0, 6))
        self._admin_checked(worker, ("mkdir", "--parents", "/run/lock", "/run/secrets"))
        for directory in ("/tmp", "/var/tmp", "/dev/shm", "/run/lock", "/run/secrets"):
            self._admin_checked(
                worker,
                ("find", directory, "-xdev", "-uid", str(case.uid), "-delete"),
            )
        for database in ("passwd", "group"):
            identity_check = self._worker_command(
                worker,
                ("getent", database, case.user_name),
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
            if identity_check.returncode != 2 or identity_check.stdout.strip():
                raise SandboxRuntimeError("previous case identity could not be cleared")
        for directory in ("/tmp", "/var/tmp", "/dev/shm", "/run/lock", "/run/secrets"):
            residue = self._worker_command(
                worker,
                ("find", directory, "-xdev", "-uid", str(case.uid), "-print", "-quit"),
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
            if residue.returncode != 0 or residue.stdout.strip():
                raise SandboxRuntimeError("previous case writable state could not be cleared")
        self._admin_checked(
            worker,
            (
                "find",
                str(case.root),
                "-mindepth",
                "1",
                "-maxdepth",
                "1",
                "-exec",
                "rm",
                "-rf",
                "--",
                "{}",
                "+",
            ),
        )
        if not quiesced:
            self._remove_case_cgroup(worker, case)
        if case.filesystem_source is not None:
            self._sealed_skill_catalogs.discard(case.filesystem_source)
            self._quiesced_cases.discard(case.filesystem_source)

    def _setup_case_cgroup(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        cgroup_path = self._case_cgroup_contract(worker, case)
        self._checked_case_cgroup_control(
            worker.name,
            worker.id,
            ("python3", "-c", CASE_CGROUP_SETUP_SCRIPT, str(cgroup_path)),
            "setup",
        )

    def _terminate_and_prove_case_cgroup_empty(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        self._case_cgroup_contract(worker, case)
        self._terminate_and_prove_case_cgroup_empty_by_name(
            worker.name,
            worker.id,
            case,
        )

    def _terminate_and_prove_case_cgroup_empty_by_name(
        self,
        sandbox_name: str,
        sandbox_id: str,
        case: CaseWorkspace,
    ) -> None:
        cgroup_path = self._case_cgroup_contract(None, case)
        cleanup_timeout = max(
            1,
            min(10, self.manifest.limits.preflight_timeout_seconds - 1),
        )
        self._checked_case_cgroup_control(
            sandbox_name,
            sandbox_id,
            (
                "python3",
                "-c",
                CASE_CGROUP_TERMINATE_SCRIPT,
                str(cgroup_path),
                str(cleanup_timeout),
            ),
            "emptiness",
        )

    def _remove_case_cgroup(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
    ) -> None:
        self._case_cgroup_contract(worker, case)
        self._remove_case_cgroup_by_name(worker.name, worker.id, case)

    def _remove_case_cgroup_by_name(
        self,
        sandbox_name: str,
        sandbox_id: str,
        case: CaseWorkspace,
    ) -> None:
        cgroup_path = self._case_cgroup_contract(None, case)
        self._checked_case_cgroup_control(
            sandbox_name,
            sandbox_id,
            ("python3", "-c", CASE_CGROUP_REMOVE_SCRIPT, str(cgroup_path)),
            "removal",
        )

    def _checked_case_cgroup_control(
        self,
        sandbox_name: str,
        sandbox_id: str,
        argv: tuple[str, ...],
        operation: str,
    ) -> None:
        result = self._worker_command_by_name(
            sandbox_name,
            sandbox_id,
            argv,
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if (
            result.timed_out
            or result.returncode != 0
            or result.stdout.strip()
            or result.stdout_truncated
            or result.stderr_truncated
        ):
            diagnostic = _safe_diagnostic(
                result.stderr.strip()
                or result.stdout.strip()
                or ("command timed out" if result.timed_out else "no diagnostic")
            )
            raise SandboxRuntimeError(
                f"case cgroup {operation} verification was ambiguous: {diagnostic}"
            )

    @staticmethod
    def _case_cgroup_contract(
        worker: SandboxWorker | None,
        case: CaseWorkspace,
    ) -> Path:
        cgroup_path = case.cgroup_path
        expected_parent = Path("/sys/fs/cgroup/ai-skills-evals")
        if (
            cgroup_path is None
            or cgroup_path.parent != expected_parent
            or cgroup_path.name != case.filesystem_source
            or re.fullmatch(r"[a-zA-Z0-9.+-]+", cgroup_path.name) is None
            or (worker is not None and case.root.parent != worker.host_root)
        ):
            raise SandboxRuntimeError("case cgroup contract is incomplete")
        return cgroup_path

    def _clear_case_ipc(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self._clear_case_ipc_by_name(worker.name, worker.id, case)

    def _clear_case_ipc_by_name(
        self,
        sandbox_name: str,
        sandbox_id: str,
        case: CaseWorkspace,
    ) -> None:
        result = self._worker_command_by_name(
            sandbox_name,
            sandbox_id,
            ("python3", "-c", IPC_CLEANUP_SCRIPT, str(case.uid)),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if (
            result.timed_out
            or result.returncode != 0
            or result.stdout.strip()
            or result.stderr.strip()
            or result.stdout_truncated
            or result.stderr_truncated
        ):
            raise SandboxRuntimeError("case IPC cleanup verification was ambiguous")

    def _admin_checked(
        self,
        worker: SandboxWorker,
        argv: Sequence[str],
        *,
        accepted: tuple[int, ...] = (0,),
    ) -> CommandResult:
        result = self._worker_command(
            worker,
            argv,
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if result.timed_out or result.returncode not in accepted:
            diagnostic = _safe_diagnostic(
                result.stderr.strip()
                or result.stdout.strip()
                or ("command timed out" if result.timed_out else "no diagnostic")
            )
            raise SandboxRuntimeError(
                f"case identity command failed: {argv[0]}: {diagnostic}"
            )
        return result

    def _case_user_checked(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        argv: Sequence[str],
        failure: str,
    ) -> None:
        cgroup_path = self._case_cgroup_contract(worker, case)
        result = self._worker_command(
            worker,
            (
                "python3",
                "-c",
                CASE_CGROUP_EXEC_SCRIPT,
                str(cgroup_path),
                str(case.uid),
                *argv,
            ),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if result.timed_out or result.returncode != 0:
            diagnostic = _safe_diagnostic(
                result.stderr.strip()
                or result.stdout.strip()
                or ("command timed out" if result.timed_out else "no diagnostic")
            )
            raise SandboxRuntimeError(f"{failure}: {diagnostic}")

    def _worker_command(
        self,
        worker: SandboxWorker,
        argv: Sequence[str],
        *,
        user: str,
        timeout_seconds: int,
    ) -> CommandResult:
        self._require_owned_worker(worker)
        return self._worker_command_by_name(
            worker.name,
            worker.id,
            argv,
            user=user,
            timeout_seconds=timeout_seconds,
        )

    def _worker_command_by_name(
        self,
        sandbox_name: str,
        sandbox_id: str,
        argv: Sequence[str],
        *,
        user: str,
        timeout_seconds: int,
    ) -> CommandResult:
        self._require_exact_live_identity(sandbox_name, sandbox_id)
        command = ("sbx", "exec", "--user", user, sandbox_name, *argv)
        return self.process.run(command, timeout_seconds=timeout_seconds)

    def __enter__(self) -> SandboxRuntime:
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def _checked(self, argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        result = self.process.run(argv, timeout_seconds=timeout_seconds)
        if not result.process_outcome.fully_terminated_and_reaped:
            error = SandboxRuntimeError(
                f"command process cleanup was not proven: {' '.join(argv[:2])}"
            )
            _attach_process_outcome(error, result.process_outcome)
            raise error
        if result.timed_out:
            error = SandboxRuntimeError(f"command timed out: {' '.join(argv[:2])}")
            _attach_process_outcome(error, result.process_outcome)
            raise error
        if result.returncode != 0:
            diagnostic = _safe_diagnostic(result.stderr.strip() or result.stdout.strip() or "no diagnostic")
            error = SandboxRuntimeError(
                f"command failed: {' '.join(argv[:2])}: {diagnostic}"
            )
            _attach_process_outcome(error, result.process_outcome)
            raise error
        return result

    def _json_command(self, argv: tuple[str, ...], timeout_seconds: int) -> Mapping[str, object]:
        result = self._checked(argv, timeout_seconds)
        try:
            return _mapping(json.loads(result.stdout), "sbx JSON output")
        except json.JSONDecodeError as error:
            raise SandboxRuntimeError(f"invalid JSON from {' '.join(argv[:2])}") from error

    def _list_sandboxes(self) -> list[Mapping[str, object]]:
        payload = self._json_command(
            ("sbx", "ls", "--json"), self.manifest.limits.preflight_timeout_seconds
        )
        raw_items = payload.get("sandboxes")
        if not isinstance(raw_items, list) or not all(isinstance(item, Mapping) for item in raw_items):
            raise SandboxRuntimeError("sbx ls --json returned an invalid sandbox list")
        return list(raw_items)

    def _verify_template(self, payload: Mapping[str, object]) -> None:
        raw_images = payload.get("images")
        if not isinstance(raw_images, list):
            raise SandboxRuntimeError("sbx template ls --json returned an invalid image list")
        image_with_tag, digest = self.manifest.codex.template.rsplit("@sha256:", 1)
        repository, tag = image_with_tag.rsplit(":", 1)
        for image in raw_images:
            if not isinstance(image, Mapping):
                continue
            image_id = image.get("id")
            if (
                image.get("repository") == repository
                and image.get("tag") == tag
                and isinstance(image_id, str)
                and re.fullmatch(r"[0-9a-f]{12}", image_id) is not None
                and digest.startswith(image_id)
            ):
                return
        raise SandboxRuntimeError("pinned Codex template digest is not available")

    def _probe_results_root(self) -> None:
        probe = self.results_root / f".ai-skills-preflight-{self.invocation_id}"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                probe,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            os.write(descriptor, b"probe\n")
            os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.read(descriptor, 64) != b"probe\n":
                raise OSError("result root probe could not be read back")
            os.close(descriptor)
            descriptor = None
            probe.unlink()
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
            raise SandboxRuntimeError("durable result root write/delete probe failed") from error

    def _verify_network_policy(self, payload: Mapping[str, object]) -> None:
        raw_rules = payload.get("rules")
        if not isinstance(raw_rules, list):
            raise SandboxRuntimeError("sbx policy ls --json returned an invalid rule list")
        policy = self.manifest.sbx.network_policy
        by_id = {
            rule.get("id"): rule
            for rule in raw_rules
            if isinstance(rule, Mapping) and isinstance(rule.get("id"), str)
        }
        for rule_id in policy.required_rule_ids:
            rule = by_id.get(rule_id)
            if (
                not isinstance(rule, Mapping)
                or rule.get("policy_id") != policy.policy_id
                or rule.get("resource_type") != "network"
                or rule.get("decision") != "allow"
                or rule.get("origin") != "local"
                or rule.get("status") != "active"
            ):
                raise SandboxRuntimeError("active policy does not match the balanced preset")
        model_resources = by_id["default-ai-services"].get("resources")
        required_model_routes = {
            "**.openai.com:443",
            "chatgpt.com:443",
            "**.chatgpt.com:443",
        }
        if not isinstance(model_resources, list) or not required_model_routes.issubset(model_resources):
            raise SandboxRuntimeError("balanced policy does not expose the exact OpenAI model routes")
        if network_policy_sha256(payload) != policy.rules_sha256:
            raise SandboxRuntimeError("active balanced policy rule set does not match its immutable pin")


def network_policy_sha256(payload: Mapping[str, object]) -> str:
    """Hash the complete active network rule contract in a stable representation."""
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise SandboxRuntimeError("sbx policy ls --json returned an invalid rule list")
    normalized: list[dict[str, object]] = []
    identifiers: set[str] = set()
    scalar_fields = (
        "id",
        "policy_id",
        "scope",
        "applies_to",
        "resource_type",
        "decision",
        "origin",
        "status",
    )
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, Mapping):
            raise SandboxRuntimeError("sbx policy rule must be an object")
        values = {field: raw_rule.get(field) for field in scalar_fields}
        if not all(isinstance(value, str) and value for value in values.values()):
            raise SandboxRuntimeError("sbx policy rule metadata is invalid")
        identifier = values["id"]
        assert isinstance(identifier, str)
        if identifier in identifiers:
            raise SandboxRuntimeError("sbx policy rule identifiers must be unique")
        identifiers.add(identifier)
        resources = raw_rule.get("resources")
        if (
            not isinstance(resources, list)
            or not resources
            or not all(isinstance(resource, str) and resource for resource in resources)
            or len(resources) != len(set(resources))
        ):
            raise SandboxRuntimeError("sbx policy rule resources are invalid")
        normalized.append({**values, "resources": sorted(resources)})
    serialized = json.dumps(
        sorted(normalized, key=lambda item: str(item["id"])),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _is_pinned_binary_update_notice(
    check: Mapping[str, object],
    expected_version: str,
) -> bool:
    message = check.get("message")
    return (
        check.get("name") == "Binary version"
        and check.get("status") == "warn"
        and isinstance(message, str)
        and re.fullmatch(
            rf"update available: v\d+\.\d+\.\d+ \(running {re.escape(expected_version)}\)",
            message,
        )
        is not None
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ManifestError(f"{label} must be a JSON object")
    return value


def _section(parent: Mapping[str, object], key: str, expected: set[str]) -> Mapping[str, object]:
    section = _mapping(parent.get(key), key)
    _expect_keys(section, expected, key)
    return section


def _expect_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise ManifestError(f"{label} has unknown keys: {', '.join(unknown)}")
    if missing:
        raise ManifestError(f"{label} is missing keys: {', '.join(missing)}")


def _string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ManifestError(f"{key} must be a non-empty string")
    return item


def _plain_version(value: Mapping[str, object], key: str) -> str:
    item = _string(value, key)
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", item):
        raise ManifestError(f"{key} must be an exact semantic version")
    return item


def _hex_string(value: Mapping[str, object], key: str, length: int) -> str:
    item = _string(value, key)
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", item):
        raise ManifestError(f"{key} must be {length} lowercase hexadecimal characters")
    return item


def _integer(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ManifestError(f"{key} must be an integer")
    return item


def _positive_integer(value: Mapping[str, object], key: str) -> int:
    item = _integer(value, key)
    if item <= 0:
        raise ManifestError(f"{key} must be positive")
    return item


def _boolean(value: Mapping[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ManifestError(f"{key} must be a boolean")
    return item


def _string_tuple(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or not item or not all(isinstance(part, str) and part for part in item):
        raise ManifestError(f"{key} must be a non-empty string array")
    return tuple(item)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("duplicate JSON object key")
        payload[key] = value
    return payload


def _matches_exact_shape(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            _matches_exact_shape(actual[key], value)
            for key, value in expected.items()
        )
    return actual == expected


def _safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9.+-]+", "-", value).strip("-")
    if not cleaned:
        raise SandboxRuntimeError("invocation id must contain a sandbox-safe character")
    return cleaned[:48]


def _grant_owner_directory_removal_access(root: Path) -> None:
    """Make a destroyed worker's real directories removable without following links."""

    def grant(path: Path) -> None:
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise SandboxRuntimeError("worker host staging contains an invalid directory")
        os.chmod(
            path,
            stat.S_IMODE(metadata.st_mode)
            | stat.S_IRUSR
            | stat.S_IWUSR
            | stat.S_IXUSR,
        )

    grant(root)

    def reject_walk_error(error: OSError) -> None:
        raise error

    for directory, child_names, _ in os.walk(
        root,
        topdown=True,
        onerror=reject_walk_error,
        followlinks=False,
    ):
        current = Path(directory)
        grant(current)
        traversable: list[str] = []
        for name in child_names:
            child = current / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                raise SandboxRuntimeError("worker host staging directory changed during cleanup")
            grant(child)
            traversable.append(name)
        child_names[:] = traversable


def _safe_diagnostic(value: str) -> str:
    return bounded_redacted_runtime_text(value, CLEANUP_FAILURE_MAXIMUM_BYTES)


def _cleanup_failure_diagnostic(
    pending: Sequence[CleanupTarget],
    failures: Mapping[str, Sequence[BaseException]],
) -> str:
    details: list[str] = []
    for target in pending:
        target_failures = failures.get(target.name) or (
            SandboxRuntimeError("cleanup did not complete"),
        )
        detail = " | ".join(str(error) for error in target_failures)
        details.append(
            f"{target.name}: "
            f"{bounded_redacted_runtime_text(detail, CLEANUP_TARGET_FAILURE_MAXIMUM_BYTES)}"
        )
    return bounded_redacted_runtime_text(
        "sandbox cleanup incomplete: " + "; ".join(details),
        CLEANUP_FAILURE_MAXIMUM_BYTES,
    )
