# Agent Instructions

This repository is the tracked source for personal AI skills used across multiple agents (Claude Code, Codex, and any future agent). It is **not** a place to maintain parallel per-agent copies of the same skill.

## Repository rules

### 1. One canonical copy per skill

Maintain a **single canonical version** of each skill in this repo. Do not fork a skill into per-agent folders (`claude/skills/foo/` *and* `codex/skills/foo/`). Forked copies drift, fixes don't propagate, and the same bug ends up debugged twice.

If you encounter an existing duplicated skill (the same skill present under both `claude/skills/` and `codex/skills/`), prefer to **consolidate** it into one canonical location before making further edits, and call this out to the user.

The canonical layout the repo is migrating toward:

```
skills/
└── <skill-name>/
    ├── SKILL.md
    ├── scripts/
    ├── references/
    └── adapters/        # only if truly needed; see rule 5 below

plugins/
└── <plugin-name>/
    ├── skills/
    │   └── <skill-name>/
    │       ├── SKILL.md
    │       ├── scripts/
    │       ├── references/
    │       ├── tests/
    │       └── agents/   # optional thin harness metadata only
    ├── .codex-plugin/
    └── .claude-plugin/
```

Until the migration is complete, the legacy `claude/skills/` and `codex/skills/` trees may still contain skills. New skills should be authored in the canonical location.

### 2. Sync to both install directories on every change

Every change to a canonical skill must be propagated to **both** agent install directories in the same flow:

- `~/.codex/skills/<skill-name>/`
- `~/.claude/skills/<skill-name>/`

Use the repo-level sync script; do not add per-skill `_sync.sh` wrappers:

```bash
python3 scripts/sync_skill.py push <skill-name>
python3 scripts/sync_skill.py pull <skill-name> claude|codex
```

Treat the sync as part of the edit — not a follow-up. If a change lands in the repo but only one install dir gets updated, the agents are now running different versions of the skill, which is exactly the situation the single-canonical-copy rule exists to prevent.

For legacy skills that still live under `claude/skills/` or `codex/skills/`, the same applies: the edit in the repo and the corresponding update under `~/.claude/skills/` or `~/.codex/skills/` must happen together.

### 3. Plugin packaging and harness-specific plumbing

Plugin-packaged skills follow the same one-canonical-copy rule. The portable skill content lives under `plugins/<plugin-name>/skills/<skill-name>/`; do not duplicate those `SKILL.md` files into per-agent source folders.

Treat these paths as generic, portable plugin content:

- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md`
- `plugins/<plugin-name>/skills/<skill-name>/scripts/`
- `plugins/<plugin-name>/skills/<skill-name>/references/`
- `plugins/<plugin-name>/skills/<skill-name>/tests/`
- plugin-level docs or evaluations under `plugins/<plugin-name>/`

Treat these paths as harness-specific distribution metadata:

- `plugins/<plugin-name>/.codex-plugin/plugin.json` for Codex plugin discovery.
- `.agents/plugins/marketplace.json` for the repo-local Codex marketplace registry. Add or update entries here when a plugin should be available from this repo.
- `plugins/<plugin-name>/skills/<skill-name>/agents/openai.yaml` for optional OpenAI/Codex skill interface metadata. Keep this declarative and thin.
- `plugins/<plugin-name>/.claude-plugin/plugin.json` for Claude Code plugin metadata.
- `plugins/<plugin-name>/.claude-plugin/marketplace.json` for the Claude Code local plugin marketplace entry.

Harness metadata is not the skill's domain knowledge. Keep it minimal, declarative, and synchronized with the actual plugin name, version, description, and skill list. If metadata begins to contain process guidance, move that guidance back into the canonical skill.

Do not edit installed plugin caches as source of truth. Paths such as `~/.codex/plugins/cache/...` and `~/.claude/plugins/cache/...` are derived install artifacts; refresh them from the repo or local plugin source instead.

### 4. Installing or refreshing plugins across harnesses

When adding or updating a plugin, handle all three layers in the same change:

1. Update the canonical repo source under `plugins/<plugin-name>/`.
2. Update harness metadata for every supported harness in the repo.
3. Refresh the local installs that agents actually read.

For Codex availability:

- Keep `plugins/<plugin-name>/.codex-plugin/plugin.json` in the plugin root.
- Keep `.agents/plugins/marketplace.json` pointing at the repo plugin source, usually `./plugins/<plugin-name>`.
- For repo-local testing, the Codex marketplace root is the repo root because `.agents/plugins/marketplace.json` lives there.
- For user-wide local installation, copy the plugin to `~/plugins/<plugin-name>/`, keep `~/.agents/plugins/marketplace.json` pointing at `./plugins/<plugin-name>`, then add or upgrade the `~` marketplace root.
- Refresh `~/.codex/skills/<skill-name>/` for each plugin skill when Codex sessions also rely on direct skill discovery.

For Claude Code availability:

- Keep `plugins/<plugin-name>/.claude-plugin/plugin.json` and `plugins/<plugin-name>/.claude-plugin/marketplace.json` in the plugin root.
- Validate the plugin before claiming it is installable.
- Refresh the durable local plugin copy, usually `~/plugins/<plugin-name>/`.
- Add or update the Claude marketplace source that contains `.claude-plugin/marketplace.json`, then install or update the plugin from that marketplace.
- Refresh `~/.claude/skills/<skill-name>/` for each plugin skill when Claude sessions also rely on direct skill discovery.

For direct skill install directories, copy the canonical skill folder exactly, including scripts, references, tests, and thin `agents/` metadata if present. Do not hand-edit the installed copy and then forget to pull it back into the repo.

Useful local refresh commands for the current plugin convention:

```bash
rsync -a --delete plugins/<plugin-name>/ "$HOME/plugins/<plugin-name>/"
rsync -a --delete plugins/<plugin-name>/skills/<skill-name>/ "$HOME/.codex/skills/<skill-name>/"
rsync -a --delete plugins/<plugin-name>/skills/<skill-name>/ "$HOME/.claude/skills/<skill-name>/"

codex plugin marketplace add "$HOME"
codex plugin marketplace upgrade local

claude plugin validate "$HOME/plugins/<plugin-name>"
claude plugin marketplace add "$HOME/plugins/<plugin-name>"
claude plugin install <plugin-name>@<marketplace-name> --scope user
claude plugin update <plugin-name> --scope user
```

Use the install command for a new Claude plugin and the update command for an already installed one. If a command reports the marketplace or plugin already exists, run the corresponding update/upgrade command instead of creating a duplicate entry.

### 5. Prefer Python for repo automation

Use Python stdlib for repo-level automation with branching logic, validation, or filesystem mutation. Reserve shell scripts for tiny command wrappers.

### 6. Authoring rules

All skills authored or modified in this repository must follow the [Rules for Writing Cross-Agent Skills](#rules-for-writing-cross-agent-skills) below.

### 7. Trigger scenarios for every skill change

Every new skill and every update to an existing skill must add or update trigger coverage in `tests/skill-trigger/scenarios.toml`. The scenario should capture the real user phrasing, repository context, provider/tool context, or failure mode that should make the skill get picked up.

Do not treat trigger testing as optional documentation. If a skill's `description`, "When to Use" section, scope, or invocation behavior changes, update the trigger scenario registry in the same change.

### 8. Run trigger tests before PR creation

Before creating a PR for any skill addition or skill update, run the deterministic trigger contract and the behavioral trigger pressure suite:

```bash
python3 tests/skill-trigger/static_contract.py
SKILL_TRIGGER_AGENT_COMMAND='<command reading stdin>' \
  python3 tests/skill-trigger/behavioral_pressure.py
```

The behavioral command should use the target agent/runtime whose skill selection matters for the PR. If the behavioral suite cannot be run, do not silently proceed; report the exact blocker and get explicit user approval before creating the PR.

---

# Rules for Writing Cross-Agent Skills

These rules apply when authoring a skill (instructions, recipes, or workflows) intended to run on more than one agent — Claude Code, Codex, Cursor, or any future agent. The goal is one source of truth, written at the right level of abstraction. **Maintain a single canonical skill; don't fork it per agent.**

## Core principle

The agent figures out the tools. The skill teaches the craft.

Keep the skill's center of gravity on the part that's actually hard — domain expertise, gotchas, output quality — and push agent-specific glue out to the thinnest possible edge.

## Rules

### 1. Separate domain knowledge from the delivery layer

Every skill contains two kinds of content:

- **Domain knowledge** — how to produce a good X. What library to use, what the output should look like, what pitfalls to avoid, what good looks like. This is portable across every agent.
- **Delivery layer** — how to invoke the agent's tools. Tool names, file paths, prompt syntax. This is the fragile part.

Spend your effort on domain knowledge. Keep the delivery layer minimal and replaceable.

### 2. Write at the level of intent, not tool names

Describe what to do, not which tool to call.

- ❌ "Use the `Read` tool to open the file."
- ✅ "Open and inspect the file."
- ❌ "Call `ask_user_input_v0` to get their preferences."
- ✅ "Ask the user about their preferences before proceeding."
- ❌ "Use `str_replace` to update the import statement."
- ✅ "Update the import statement in place."

Any reasonable agent maps intent to its native capability. This also future-proofs against tool renames within a single agent.

### 3. Default to the shell/filesystem substrate

Almost every agent can execute shell commands and read/write files. When work is non-trivial, put it in a script the agent invokes:

```
my-skill/
├── SKILL.md
├── scripts/
│   ├── validate.py
│   └── render.sh
└── references/
    └── examples.md
```

The agent's role becomes "decide when to invoke this script and how to interpret the output" — a capability every agent has. The skill body stays short and the heavy lifting lives in code, which is genuinely portable.

### 4. For divergent capabilities, write fallback chains

Some capabilities (screenshots, browser automation, image generation, MCP integrations) exist on some agents and not others. Phrase these as a degradation ladder, never as an assumption:

> Prefer a native screenshot capability if one exists. Otherwise, render the HTML to disk and capture it via Playwright through the shell. If neither is available, save the file and ask the user to confirm visually.

This pattern works on the agent you're using today and on the one you haven't tested yet.

### 5. Use adapter files only as a last resort

If a skill truly needs per-agent overrides, keep one canonical `SKILL.md` plus thin adapter files referenced from the main body:

```
my-skill/
├── SKILL.md
└── adapters/
    ├── claude-code.md
    ├── cursor.md
    └── codex.md
```

Fight to keep adapters tiny. They are platform-specific code and they will rot. If an adapter is growing past ~30 lines, the abstraction in the main `SKILL.md` is probably wrong — fix that instead.

### 6. Do not fork the SKILL.md per agent

Maintaining three full copies of a skill is the trap this whole document exists to prevent. Forked copies diverge silently, fixes don't propagate, and the same bug gets debugged three times. The abstraction tax of writing things in agent-neutral language pays for itself the first time you fix a typo and have it stick everywhere.

### 7. Name capabilities, not products

When you must reference an external capability, name the category, not the specific product or tool:

- ❌ "Open Chrome DevTools and inspect the network tab."
- ✅ "Inspect the page's network requests."
- ❌ "Run `pytest` to verify the changes."
- ✅ "Run the project's test suite to verify the changes." (then check `package.json`, `pyproject.toml`, etc.)

### 8. Encode assumptions as preconditions, not silent expectations

If the skill genuinely requires a capability the agent might not have, say so at the top so the agent can fail fast or pick a different approach:

> Requires: ability to execute shell commands; a Node.js runtime on PATH; write access to the working directory.

Anything not in this list should have a fallback.

### 9. Keep examples agent-neutral

When showing the agent how to do something, use generic phrasing in the example:

- ❌ "After running `Read('/path/to/file')`, the file appears in context. Then call `Edit(...)`."
- ✅ "After reading the file, modify the relevant section in place."

If you must show concrete syntax, show it as shell or as language-level code (`python script.py`), not as agent-specific tool calls.

### 10. Test in every target environment before claiming portability

A skill is not portable until it has actually run in each environment you care about. "Written abstractly" is necessary but not sufficient — capability gaps and prompt-format quirks only show up when you run it. Keep a short list of test prompts in `tests/` and run them when you change the skill.

## Decision heuristics

When in doubt, ask:

- "Could this same sentence work on an agent I've never seen?" If no, abstract it.
- "Is this teaching the craft or wiring up a tool?" If the latter, push it out to a script or remove it.
- "Am I describing a goal or a mechanism?" Goals are portable; mechanisms are not.
- "What happens if this capability isn't available?" If the answer is "the skill breaks," write a fallback.

## Self-review checklist

Before committing a skill, walk through this list:

- [ ] No specific tool names from any agent appear in the prose (`Read`, `Write`, `Edit`, `str_replace`, `ask_user_input_v0`, etc.).
- [ ] Non-trivial logic lives in scripts under the skill folder, not in the prose.
- [ ] Every capability that might not exist (screenshots, browser, network, MCP) has a fallback chain.
- [ ] Required capabilities are declared at the top.
- [ ] The skill has been run end-to-end on at least one target agent.
- [ ] Trigger scenarios were added or updated in `tests/skill-trigger/scenarios.toml`.
- [ ] The static trigger contract passed.
- [ ] The behavioral trigger pressure suite passed for the target agent/runtime, or the user explicitly approved the documented blocker before PR creation.
- [ ] No copy of this skill exists for a different agent. (If it does, merge them.)
- [ ] Adapter files, if any, are under ~30 lines each.
- [ ] The change has been synced to both `~/.codex/skills/` and `~/.claude/skills/` (see repo rule 2).

## Anti-patterns to refuse

If asked to do any of the following while authoring a skill, push back:

- "Just make a Claude Code version and a Cursor version." → Propose one skill with thin adapters or fallback chains.
- "Hardcode the tool name, it's faster." → Cheaper today, more expensive next month. Use intent language.
- "Skip the fallback, this agent always has X." → Capabilities get removed, renamed, or rate-limited. Always provide a fallback for non-core capabilities.
- "Put the logic in the prose so the agent reasons through it each time." → Move deterministic logic to a script. The model is not where reliability lives.
