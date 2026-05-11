# Linear MCP Proxy — Design Spec

**Date:** 2026-05-11
**Status:** Approved design, pending implementation plan
**Branch:** `ticket-start-bot-identity` (extends PR #2 in place; not a new PR)
**Predecessor specs:**
- `2026-05-10-ticket-start-bot-identity-design.md` (the bot-identity skill we just built)

## 1. Goals and non-goals

### Goals

Replace today's brittle "inject bot's Bearer token into MCP client configs" approach with a small local HTTP proxy that handles the bot's Linear OAuth lifecycle invisibly:

- **All existing Linear MCP tools work unchanged.** The agent calls `mcp__linear__*` exactly as it does today. No skill design change.
- **Bot identity preserved.** Linear continues to see the `eduard-agent` actor on every mutation.
- **Zero manual token rotation.** The proxy mints fresh tokens from the long-lived `client_id` + `client_secret` (already in Keychain) at startup and on 401. The 30-day token expiry becomes invisible.
- **No app restarts on token rotation.** Restarts only matter when the MCP server URL changes (one time, at install).
- **No on-disk copy of the bot's access token.** The proxy holds it in process memory only.

### Non-goals

- Not building an authoring/development MCP framework. The proxy is a single-purpose HTTP forwarder for `mcp.linear.app`.
- Not replacing the hosted Linear MCP server. The proxy stands *in front of* it, forwards traffic, injects auth.
- Not adding multi-account / multi-workspace support. One bot, one workspace, one OAuth app — same scope as PR #2.
- Not adding TLS to the proxy. Loopback only (`127.0.0.1:5765`). The link from proxy to upstream is HTTPS.
- Not solving rotation for the *long-lived* client_secret. That's user-rotated through the Linear OAuth app's settings UI; outside this scope.
- Not introducing job-workflow proxying. Bot identity is personal-only; same scope as PR #2.

## 2. Architecture summary

A long-running Python process listens on `127.0.0.1:5765`, accepts MCP Streamable-HTTP requests from Codex and Claude Code, injects a Bearer token (managed in process memory), forwards to `https://mcp.linear.app/mcp`, and streams the SSE response back to the client.

```
[Codex / Claude Code]
    ↓ HTTP POST /mcp; Accept: text/event-stream
[127.0.0.1:5765 — linear-mcp-proxy]
    ┌─────────────────────────────────────┐
    │ At startup:                         │
    │   read ai-skills.linear-bot.*       │
    │       from Keychain                 │
    │   mint access_token via             │
    │       /oauth/token (client_creds)   │
    │   keep in process memory            │
    │                                     │
    │ Per request:                        │
    │   strip incoming Authorization      │
    │   inject Authorization: Bearer …    │
    │   forward to upstream               │
    │   stream SSE response back          │
    │                                     │
    │ On upstream 401:                    │
    │   mint fresh token                  │
    │   retry the same request once       │
    │   return that response              │
    └─────────────────────────────────────┘
    ↓ HTTPS POST; Authorization: Bearer …
[https://mcp.linear.app/mcp]
```

A LaunchAgent (`~/Library/LaunchAgents/com.<USER>.linear-mcp-proxy.plist`) starts the proxy at user login, restarts it on crash. Logs go to `~/Library/Logs/linear-mcp-proxy.err.log`.

## 3. Architectural decisions (locked from brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| Language + libraries | Python 3.9+ with `aiohttp` | macOS ships Python; `aiohttp` makes streaming SSE proxying trivial. Isolated in venv so no system-Python pollution. |
| Transport — client side | HTTP on `127.0.0.1:5765` | Codex's TOML and CC's JSON both speak HTTP MCP; loopback-only avoids network exposure. |
| Transport — upstream side | HTTPS (mcp.linear.app's native) | Matches Linear's published transport. |
| Process management | LaunchAgent (`RunAtLoad: true`, `KeepAlive: true`) | macOS-native, auto-starts on login, auto-restarts on crash. |
| Token storage | Process memory only | No on-disk copy; restart = fresh mint = same outcome as "rotate". |
| Token mint cadence | Startup + on-401 retry | No periodic background refresh. Personal-use proxy; either approach works but reactive is simpler and avoids a background coroutine. |
| Auth scheme to upstream | `Authorization: Bearer <token>` | What Linear's MCP server accepts per docs. |
| Auth scheme to clients | Nothing (loopback trust) | Anyone with shell access to this machine can already hit the proxy; we don't gain security by requiring a header. |
| Failure mode | Fail closed + surface error | Missing Keychain entries, token-mint failure → proxy exits non-zero; LaunchAgent log surfaces it. No silent fallback. |
| Cleanup at install | Delete legacy access-token Keychain entry; strip Bearer headers from MCP configs; switch URLs to localhost | Required by user's "no legacy" mandate. |
| Skill files removed | `linear-oauth-bootstrap.sh`, `update-linear-mcp-configs.sh` | Obsolete with the proxy. |
| Proxy file location | `~/Library/Application Support/ai-skills/linear-mcp-proxy/` | macOS conventional location for app data; copied here at install time so the running proxy is decoupled from `git pull` on the skill repo. |
| Venv location | `~/Library/Application Support/ai-skills/linear-mcp-proxy/.venv/` | Same parent directory; one cohesive install. |

## 4. The proxy process (`linear-mcp-proxy.py`)

### Behavior

1. **Startup**
   - Read `USER` env var (fall back to `id -un`).
   - Call `security find-generic-password -s ai-skills.linear-bot.client-id -a "$USER" -w` (and same for `.client-secret`). Apply the hex-decode workaround if Keychain returns a hex-encoded value (same logic as `get-bot-gh-token.sh`).
   - POST to `https://api.linear.app/oauth/token` with `grant_type=client_credentials`, `scope=read,write,issues:create`, the two credentials. Expect JSON with `access_token`. Store in module-level variable.
   - If any of the above fails, log to stderr and exit `1`.
   - Start aiohttp server on `127.0.0.1:5765`.

2. **`GET /healthz`**
   - Return 200 with body `ok\n`. No auth headers added. For health checks only.

3. **Any other path/method**
   - Strip incoming `Authorization`, `Host`, `Content-Length`, `Connection` headers.
   - Copy remaining headers as-is (preserves `mcp-session-id`, `Content-Type: application/json`, `Accept: text/event-stream`, etc.).
   - Add `Authorization: Bearer <token>`.
   - Forward to `https://mcp.linear.app<original-path>` with the original method and body.
   - Stream the upstream response back to the client as it arrives (SSE chunks pass through end-to-end).
   - If upstream returns `401`: mint a fresh token (synchronously — block the request), retry the request once with the new token, return that response. If the retry also returns 401, return the 401 to the client.
   - If upstream is unreachable or returns 5xx: return `502 Bad Gateway` to the client with a short text body. Log to stderr.

4. **Logging**
   - Module-level `logging.basicConfig(level=logging.INFO, format='%(asctime)s [linear-mcp-proxy] %(message)s')`.
   - All logs to stderr; LaunchAgent captures.
   - Log lines: startup banner with port and upstream; "Initial token minted"; "Upstream returned 401; minting fresh token"; "Token mint failed: <error>"; "Forward error: <error>". Never log the token itself.

### Environment variables

| Var | Default | Purpose |
|---|---|---|
| `LINEAR_MCP_PROXY_PORT` | `5765` | Override the bind port (rarely needed; for testing or port conflicts). |
| `LINEAR_MCP_UPSTREAM` | `https://mcp.linear.app/mcp` | Override upstream (testing). |
| `USER` | (from process env) | Used to look up Keychain entries. |

### Code size estimate

~100 lines of Python including comments and error handling. Single file, no module structure.

## 5. The LaunchAgent (`linear-mcp-proxy.plist.template`)

A plist template with placeholders for `$USER`, `$HOME`, and the venv's Python interpreter path. The install script substitutes these and writes the result to `~/Library/LaunchAgents/com.$USER.linear-mcp-proxy.plist`.

Relevant keys:

| Key | Value | Purpose |
|---|---|---|
| `Label` | `com.<USER>.linear-mcp-proxy` | Unique identifier. |
| `ProgramArguments` | `[<venv-python>, <proxy-path>]` | The Python interpreter inside the venv runs the proxy script. |
| `RunAtLoad` | `true` | Start at login. |
| `KeepAlive` | `true` | Auto-restart on crash. |
| `ProcessType` | `Background` | Low priority; doesn't appear in user-facing lists. |
| `StandardErrorPath` | `~/Library/Logs/linear-mcp-proxy.err.log` | Where stderr (all our logs) goes. |
| `StandardOutPath` | `/dev/null` | Proxy doesn't write to stdout. |
| `EnvironmentVariables.PATH` | `/usr/bin:/bin:/usr/sbin:/sbin` | Pins `security` (Keychain CLI) so the proxy can find it under launchd's restricted env. |
| `EnvironmentVariables.LINEAR_MCP_PROXY_PORT` | `5765` | Default port; overrideable. |

Loaded via `launchctl bootstrap gui/$UID <plist>`. Unloaded via `launchctl bootout gui/$UID/com.$USER.linear-mcp-proxy`.

## 6. Install flow (`install-linear-mcp-proxy.sh`)

Idempotent. Safe to re-run. Aborts on any failure before destructive changes happen.

### Step 1 — Pre-flight (read-only checks; aborts here if anything's wrong)

- `python3 --version` → expect ≥ 3.9
- `security find-generic-password -s ai-skills.linear-bot.client-id -a "$USER"` → exists
- `security find-generic-password -s ai-skills.linear-bot.client-secret -a "$USER"` → exists
- **Credential probe:** call `https://api.linear.app/oauth/token` directly with `grant_type=client_credentials` using the credentials. Confirm HTTP 200 and an `access_token` in the response. Discard the probe token. This is the safety net — if the user's credentials are wrong, the user finds out *before* the install touches anything else.

### Step 2 — Stage installation directory

- `mkdir -p ~/Library/Application\ Support/ai-skills/linear-mcp-proxy/`
- `python3 -m venv ~/Library/Application\ Support/ai-skills/linear-mcp-proxy/.venv`
- `~/Library/Application\ Support/ai-skills/linear-mcp-proxy/.venv/bin/pip install -r <skill-root>/scripts/linear-mcp-proxy-requirements.txt` (just `aiohttp`)
- `cp <skill-root>/scripts/linear-mcp-proxy.py ~/Library/Application\ Support/ai-skills/linear-mcp-proxy/linear-mcp-proxy.py`

### Step 3 — Write + load LaunchAgent

- Render plist template, substituting `$USER`, `$HOME`, venv-python path, proxy-script path.
- `launchctl bootout gui/$UID/com.$USER.linear-mcp-proxy 2>/dev/null || true` (idempotent unload)
- `launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.$USER.linear-mcp-proxy.plist`
- Poll `curl -sf http://127.0.0.1:5765/healthz` up to 5 seconds, 200ms intervals. Abort if no response.

### Step 4 — Repoint MCP client configs

- `~/.codex/config.toml`: under `[mcp_servers.linear]`, remove any `http_headers` line, set `url = "http://localhost:5765/mcp"`.
- `~/.claude.json`: walk to every `mcpServers.linear` occurrence (global + each project's). For each: remove `headers` field, set `url` to `http://localhost:5765/mcp`. (Reuse the parsing pattern from PR #2's `update-linear-mcp-configs.sh` — but inverted.)

### Step 5 — Legacy cleanup

- `security delete-generic-password -s ai-skills.linear-bot.access-token -a "$USER" 2>/dev/null || true` (idempotent — silent if doesn't exist).

### Step 6 — Final verification

- `curl -sf http://127.0.0.1:5765/healthz` → 200 "ok"
- Identity probe **through the proxy**: an MCP `initialize` + `tools/call` for the appropriate viewer-returning tool. Confirm the returned user has email `*@oauthapp.linear.app`.

### Step 7 — Final output

```
✓ Linear MCP proxy installed.
  Process: <pid> on 127.0.0.1:5765
  Logs: ~/Library/Logs/linear-mcp-proxy.err.log

NEXT STEPS:
1. Restart Codex and Claude Code so they pick up the new MCP URL.
2. After restart, run check-linear-mcp-proxy.sh anytime to verify health.

UNINSTALL: run uninstall-linear-mcp-proxy.sh
```

## 7. Uninstall flow (`uninstall-linear-mcp-proxy.sh`)

Reverses install but does **not** remove credentials, the Linear OAuth app on Linear's side, or other bot-identity setup.

1. **Stop the LaunchAgent**
   - `launchctl bootout gui/$UID/com.$USER.linear-mcp-proxy 2>/dev/null || true`
   - `rm -f ~/Library/LaunchAgents/com.$USER.linear-mcp-proxy.plist`

2. **Restore MCP client configs**
   - `~/.codex/config.toml`: switch `url` back to `https://mcp.linear.app/mcp` for `[mcp_servers.linear]`. (Bearer header was already stripped; don't re-add.)
   - `~/.claude.json`: switch `url` back to `https://mcp.linear.app/mcp` for global and each project's `mcpServers.linear`.

3. **Prompt for optional cleanup**
   - `Remove venv at ~/Library/Application Support/ai-skills/linear-mcp-proxy/? [y/N]`
   - `Remove log at ~/Library/Logs/linear-mcp-proxy.err.log? [y/N]`

4. **Print restart instructions**
   - Banner: "Restart Codex and Claude Code so they re-OAuth against mcp.linear.app as your personal account."

## 8. Health-check helper (`check-linear-mcp-proxy.sh`)

Standalone diagnostic. Doesn't change anything. Output is human-readable.

```
Linear MCP Proxy — Health Check
================================

LaunchAgent loaded:    yes (PID 12345)
Process on 5765:       responding (GET /healthz → 200 ok)
Identity via proxy:    eduard-agent (<email>@oauthapp.linear.app) ✓

Last log lines (most recent 10):
  2026-05-11 17:33:01 [linear-mcp-proxy] Initial token minted successfully
  2026-05-11 17:33:01 [linear-mcp-proxy] Listening on 127.0.0.1:5765
  ...
```

Exit codes: 0 if everything OK; 1 if anything not as expected (LaunchAgent not loaded, proxy not responding, identity probe returns wrong email).

## 9. File structure changes

### New files (added in both `codex/` and `claude/` skill trees)

| File | Purpose |
|---|---|
| `scripts/linear-mcp-proxy.py` | The proxy process. |
| `scripts/linear-mcp-proxy-requirements.txt` | One line: `aiohttp`. |
| `scripts/linear-mcp-proxy.plist.template` | LaunchAgent plist with `$USER`/`$HOME`/path placeholders. |
| `scripts/install-linear-mcp-proxy.sh` | Install script (7 steps from §6). |
| `scripts/uninstall-linear-mcp-proxy.sh` | Uninstall script (§7). |
| `scripts/check-linear-mcp-proxy.sh` | Health check (§8). |

### Files removed

| File | Why |
|---|---|
| `scripts/linear-oauth-bootstrap.sh` | Obsolete. Token minting is now the proxy's job. Install script does its own credential probe. |
| `scripts/update-linear-mcp-configs.sh` | Obsolete. Proxy injects auth; no client config to push tokens into. |

### Files modified

| File | Change |
|---|---|
| `bot-identity.md` | Step C completely rewritten (proxy install/uninstall/health/troubleshooting). Step B simplified (no bootstrap-script step). Failure-mode catalog updated. Token-rotation section simplified ("no manual rotation"). All references to `access-token`/`refresh-token`/`update-linear-mcp-configs.sh` removed. |

### Files unchanged

- `SKILL.md` — Setup activation step 2 (Activate bot identity) still does the same three checks; only Check 3's mechanism is updated to "probe `localhost:5765` instead of upstream directly", but the call site is at `bot-identity.md` so no `SKILL.md` change.
- All six agent role-prompts.
- `bug-fix-loop.md`, `self-improvement.md`, `react-parity.md`, `verification.md`, `job-workflow.md`, `personal-workflow.md`.
- `agents/openai.yaml`.

### Keychain changes at install time

| Entry | Action | Why |
|---|---|---|
| `ai-skills.gh-bot.*` (5 entries) | unchanged | GitHub side; independent of Linear changes. |
| `ai-skills.linear-bot.client-id` | unchanged | Proxy reads at startup. |
| `ai-skills.linear-bot.client-secret` | unchanged | Proxy reads at startup. |
| `ai-skills.linear-bot.access-token` | **deleted** | Proxy holds tokens in memory; on-disk copy is now stale legacy state. |
| `ai-skills.linear-bot.refresh-token` | **deleted if present** | Never used by `client_credentials` flow; defensive cleanup. |

### MCP-client config changes at install time

| Config | Field | Before | After |
|---|---|---|---|
| `~/.codex/config.toml` | `[mcp_servers.linear].http_headers` | `{ Authorization = "Bearer …" }` | (removed) |
| `~/.codex/config.toml` | `[mcp_servers.linear].url` | `https://mcp.linear.app/mcp` | `http://localhost:5765/mcp` |
| `~/.claude.json` (global) | `mcpServers.linear.headers` | `{ Authorization: "Bearer …" }` | (removed) |
| `~/.claude.json` (global) | `mcpServers.linear.url` | `https://mcp.linear.app/mcp` | `http://localhost:5765/mcp` |
| `~/.claude.json` (per project) | same fields | same | same |

### Mirroring requirements

Per the user's standing sync rule (in `MEMORY.md`):
- Every edit under `codex/skills/` mirrors to `~/.codex/skills/` in the same flow.
- Every edit under `claude/skills/` mirrors to `~/.claude/skills/` in the same flow.
- Scripts must preserve executable bit (`rsync -av` does this).

Tree symmetry: only `codex/skills/ticket-start/agents/openai.yaml` is Codex-only (unchanged from PR #2).

## 10. `bot-identity.md` rewrite — Step C

The full rewrite is plan-level detail. The shape:

```
### Step C — Install the Linear MCP proxy

[Brief explanation of why a proxy: hosted MCP doesn't natively handle
bot identity / token lifecycle; the proxy bridges that gap.]

#### Install

  bash <skill-root>/scripts/install-linear-mcp-proxy.sh

[Describe what the script does — credential probe, venv, LaunchAgent,
config repoint, legacy cleanup, verification.]

[Restart Codex + Claude Code.]

#### Verify

  bash <skill-root>/scripts/check-linear-mcp-proxy.sh

[Expected output shape.]

#### Uninstall

  bash <skill-root>/scripts/uninstall-linear-mcp-proxy.sh

[Reverses install; restores client configs to mcp.linear.app
direct (re-OAuths as you on next session).]

#### Troubleshooting

[Common failure signatures + remediation: proxy not running,
identity probe shows wrong user, log tails to inspect.]
```

The Setup activation Check 3 in `bot-identity.md` is updated: the agent probes Linear MCP `get_user` through `localhost:5765` (the proxy). Result is identical (the bot's identity), but the network call is to the proxy instead of upstream.

## 11. Deferred to implementation plan

- Exact `linear-mcp-proxy.py` code (the design lays out behavior; the plan locks the exact API/SSE handling details and aiohttp idioms).
- Exact LaunchAgent plist XML structure and the templating substitution mechanism (sed? python f-string? plist library?).
- Exact MCP `tools/call` payload the install script uses for the identity probe (depends on what `get_user`-style tool the hosted MCP exposes — needs probing during implementation).
- Exact regex/parser logic for stripping `http_headers` from TOML and `headers` from JSON. (PR #2's `update-linear-mcp-configs.sh` had this; we copy + invert.)
- Whether the install script should be split into smaller sub-scripts (one-script vs phased) — judgment call at plan time.
- Whether `linear-mcp-proxy.py` should include a `--probe` CLI flag that does the same identity probe as `check-linear-mcp-proxy.sh` (to reduce duplicate code).
- Concrete test plan for the proxy (unit tests for SSE forwarding? integration test against a mock upstream? end-to-end smoke test only?). Plan-level decision.

## 12. Migration and scope

- **In scope:** new proxy + install/uninstall/check scripts + plist template + LaunchAgent setup + MCP-client config repoint + Keychain cleanup + `bot-identity.md` rewrite. All on the existing `ticket-start-bot-identity` branch, extending PR #2.
- **Out of scope:** GitHub side (unchanged), agent role-prompts (unchanged), bug-fix/self-improvement loops (unchanged), job workflow (unchanged), Linear OAuth app on Linear's side (still user-managed).
- **Migration path for the user:** the install script handles everything in one shot. No manual edits to config files or Keychain. After install + Codex/CC restart, the bot identity is live with zero ongoing rotation work.
- **Rollback:** the uninstall script reverses to "direct mcp.linear.app + user-OAuth" — same state as before any bot-identity work started. Credentials in Keychain are not deleted by uninstall (user owns those).
