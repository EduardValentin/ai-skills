#!/usr/bin/env python3
"""Generate native Codex and Claude Code agents from canonical repo agents."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


CODEX_KEYS = {
    "model",
    "model_reasoning_effort",
    "sandbox_mode",
    "nickname_candidates",
}

CLAUDE_KEYS = {
    "model",
    "effort",
    "permissionMode",
    "tools",
    "disallowedTools",
    "skills",
    "mcpServers",
    "hooks",
    "maxTurns",
    "memory",
    "background",
    "isolation",
    "color",
    "initialPrompt",
}

CLAUDE_FIELD_ORDER = (
    "model",
    "effort",
    "permissionMode",
    "tools",
    "disallowedTools",
    "skills",
    "mcpServers",
    "hooks",
    "maxTurns",
    "memory",
    "background",
    "isolation",
    "color",
    "initialPrompt",
)


@dataclass(frozen=True)
class NativeAgent:
    agent_id: str
    source: Path
    description: str
    groups: tuple[str, ...]
    preload_skills: tuple[str, ...]
    codex: dict[str, Any]
    claude: dict[str, Any]


def repo_root() -> Path:
    if override := os.environ.get("AI_SKILLS_REPO"):
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def manifest_path() -> Path:
    return repo_root() / "agents" / "manifest.toml"


def validate_agent_id(agent_id: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if not agent_id or agent_id.startswith("-") or agent_id.endswith("-"):
        raise ValueError(f"invalid agent id: {agent_id!r}")
    if "--" in agent_id or any(char not in allowed for char in agent_id):
        raise ValueError(f"invalid agent id: {agent_id!r}")
    return agent_id


def validate_relative_source(source: str) -> Path:
    path = Path(source)
    if path.is_absolute() or ".." in path.parts or not source.endswith(".md"):
        raise ValueError(f"invalid agent source: {source!r}")
    return path


def load_agents() -> list[NativeAgent]:
    path = manifest_path()
    if not path.is_file():
        raise FileNotFoundError(f"missing native agent manifest: {path}")

    data = parse_manifest(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("agents/manifest.toml must set version = 1")

    entries = data.get("agent", [])
    if not isinstance(entries, list) or not entries:
        raise ValueError("agents/manifest.toml must define at least one [[agent]]")

    agents: list[NativeAgent] = []
    seen: set[str] = set()
    for entry in entries:
        agent_id = validate_agent_id(required_string(entry, "id"))
        if agent_id in seen:
            raise ValueError(f"duplicate agent id: {agent_id}")
        seen.add(agent_id)

        source = validate_relative_source(required_string(entry, "source"))
        description = required_string(entry, "description")
        groups = string_tuple(entry.get("groups", []), f"{agent_id}.groups")
        preload_skills = string_tuple(entry.get("preload_skills", []), f"{agent_id}.preload_skills")
        codex = dict(entry.get("codex", {}))
        claude = dict(entry.get("claude", {}))
        unknown_codex = sorted(set(codex) - CODEX_KEYS - {"preload_skills"})
        unknown_claude = sorted(set(claude) - CLAUDE_KEYS)
        if unknown_codex:
            raise ValueError(f"{agent_id}.codex has unsupported keys: {', '.join(unknown_codex)}")
        if unknown_claude:
            raise ValueError(f"{agent_id}.claude has unsupported keys: {', '.join(unknown_claude)}")

        source_path = repo_root() / "agents" / source
        if not source_path.is_file():
            raise FileNotFoundError(f"missing agent source for {agent_id}: {source_path}")

        agents.append(
            NativeAgent(
                agent_id=agent_id,
                source=source,
                description=description,
                groups=groups,
                preload_skills=preload_skills,
                codex=codex,
                claude=claude,
            )
        )
    return agents


def required_string(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"agent entry missing non-empty {key}")
    return value


def string_tuple(value: Any, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{context} must be a list of non-empty strings")
    return tuple(value)


def parse_manifest(text: str) -> dict[str, Any]:
    """Parse the small TOML subset used by agents/manifest.toml.

    Python 3.11's tomllib is not available on the default macOS Python here,
    and the repo standard is stdlib-only automation. This parser intentionally
    supports only the manifest constructs we use: top-level scalar keys,
    repeated [[agent]] tables, and [agent.codex] / [agent.claude] subtables.
    """

    data: dict[str, Any] = {"agent": []}
    current: dict[str, Any] = data
    current_agent: Optional[dict[str, Any]] = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[[agent]]":
            current_agent = {}
            data["agent"].append(current_agent)
            current = current_agent
            continue
        if line in ("[agent.codex]", "[agent.claude]"):
            if current_agent is None:
                raise ValueError(f"{line_number}: subtable declared before [[agent]]")
            key = line.removeprefix("[agent.").removesuffix("]")
            current_agent.setdefault(key, {})
            current = current_agent[key]
            continue
        if line.startswith("["):
            raise ValueError(f"{line_number}: unsupported table declaration: {line}")
        if "=" not in line:
            raise ValueError(f"{line_number}: expected key = value")

        key, raw_value = line.split("=", 1)
        current[key.strip()] = parse_manifest_value(raw_value.strip(), line_number)
    return data


def parse_manifest_value(raw_value: str, line_number: int) -> Any:
    if raw_value.startswith('"') or raw_value.startswith("["):
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError as error:
            raise ValueError(f"{line_number}: invalid string/list value: {raw_value}") from error
    if raw_value in ("true", "false"):
        return raw_value == "true"
    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError(f"{line_number}: unsupported value: {raw_value}") from error


def select_agents(agents: list[NativeAgent], group: Optional[str], ids: list[str]) -> list[NativeAgent]:
    wanted = set(ids)
    selected = []
    for agent in agents:
        if group and group not in agent.groups:
            continue
        if wanted and agent.agent_id not in wanted:
            continue
        selected.append(agent)
    missing = wanted - {agent.agent_id for agent in selected}
    if missing:
        raise ValueError(f"unknown or unselected agent ids: {', '.join(sorted(missing))}")
    return selected


def generated_notice(agent: NativeAgent) -> str:
    return (
        "Generated by scripts/sync_native_agents.py from "
        f"agents/manifest.toml and agents/{agent.source.as_posix()}. "
        "Do not edit by hand."
    )


def render_codex(agent: NativeAgent) -> str:
    body = read_agent_body(agent)
    lines = [
        f"# {generated_notice(agent)}",
        'name = ' + toml_string(agent.agent_id),
        'description = ' + toml_string(agent.description),
        'developer_instructions = ' + toml_string(body),
    ]
    for key in ("model", "model_reasoning_effort", "sandbox_mode"):
        if key in agent.codex:
            lines.append(f"{key} = {toml_value(agent.codex[key])}")
    if "nickname_candidates" in agent.codex:
        lines.append(f"nickname_candidates = {toml_value(agent.codex['nickname_candidates'])}")

    preload_skills = [*agent.preload_skills, *agent.codex.get("preload_skills", [])]
    for skill_name in preload_skills:
        skill_path = Path.home() / ".codex" / "skills" / skill_name / "SKILL.md"
        lines.extend(["", "[[skills.config]]", f"path = {toml_string(str(skill_path))}"])
    return "\n".join(lines) + "\n"


def render_claude(agent: NativeAgent) -> str:
    body = read_agent_body(agent)
    frontmatter: dict[str, Any] = {
        "name": agent.agent_id,
        "description": agent.description,
    }
    for key in CLAUDE_FIELD_ORDER:
        if key in agent.claude:
            frontmatter[key] = agent.claude[key]

    skills = [*agent.preload_skills, *frontmatter.get("skills", [])]
    if skills:
        frontmatter["skills"] = skills

    lines = ["---"]
    for key, value in frontmatter.items():
        lines.extend(yaml_field(key, value))
    lines.extend(["---", f"<!-- {generated_notice(agent)} -->", "", body.rstrip(), ""])
    return "\n".join(lines)


def read_agent_body(agent: NativeAgent) -> str:
    return (repo_root() / "agents" / agent.source).read_text(encoding="utf-8")


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def toml_value(value: Any) -> str:
    if isinstance(value, str):
        return toml_string(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "[" + ", ".join(toml_string(item) for item in value) + "]"
    raise ValueError(f"unsupported TOML value: {value!r}")


def yaml_field(key: str, value: Any) -> list[str]:
    if isinstance(value, str):
        return [f"{key}: {toml_string(value)}"]
    if isinstance(value, bool):
        return [f"{key}: {'true' if value else 'false'}"]
    if isinstance(value, int):
        return [f"{key}: {value}"]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return [f"{key}:", *(f"  - {toml_string(item)}" for item in value)]
    if isinstance(value, dict):
        return [f"{key}: {json.dumps(value, sort_keys=True)}"]
    raise ValueError(f"unsupported YAML frontmatter value for {key}: {value!r}")


def codex_destination(agent: NativeAgent) -> Path:
    return Path.home() / ".codex" / "agents" / f"{agent.agent_id}.toml"


def claude_destination(agent: NativeAgent) -> Path:
    return Path.home() / ".claude" / "agents" / f"{agent.agent_id}.md"


def push(agents: list[NativeAgent]) -> None:
    for agent in agents:
        for destination, content in (
            (codex_destination(agent), render_codex(agent)),
            (claude_destination(agent), render_claude(agent)),
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
            print(f"synced native agent: {destination}")


def check(agents: list[NativeAgent]) -> None:
    for agent in agents:
        expected = {
            codex_destination(agent): render_codex(agent),
            claude_destination(agent): render_claude(agent),
        }
        for destination, content in expected.items():
            if not destination.is_file():
                raise FileNotFoundError(f"missing installed native agent: {destination}")
            actual = destination.read_text(encoding="utf-8")
            if actual != content:
                raise ValueError(f"native agent out of sync: {destination}")
            print(f"in sync: {destination}")


def render(agents: list[NativeAgent], harness: str) -> None:
    renderer = render_codex if harness == "codex" else render_claude
    for index, agent in enumerate(agents):
        if index:
            print()
        print(renderer(agent), end="")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate native Codex and Claude Code agents from agents/manifest.toml."
    )
    parser.add_argument("command", choices=("push", "check", "render"))
    parser.add_argument("agent_ids", nargs="*")
    parser.add_argument("--group", help="Only include agents tagged with this group")
    parser.add_argument("--harness", choices=("codex", "claude"), default="codex")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        selected = select_agents(load_agents(), args.group, args.agent_ids)
        if args.command == "push":
            push(selected)
        elif args.command == "check":
            check(selected)
        elif args.command == "render":
            render(selected, args.harness)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
