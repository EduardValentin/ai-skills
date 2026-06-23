# Agent Instructions

This repository is the tracked source for personal AI skills and reusable specialized agents used across multiple agents (Claude Code, Codex, and any future agent). It is **not** a place to maintain parallel per-agent copies of the same skill or agent.

## Repository rules

### Git baseline

Before creating a branch or worktree from `main`, always fetch the remote first and base the new branch/worktree on the freshly fetched `origin/main`. Do not branch from a stale local `main` ref.

### 1. One canonical copy per skill

Maintain a **single canonical version** of each skill in this repo. Do not fork a skill into per-agent folders (`claude/skills/foo/` *and* `codex/skills/foo/`). Forked copies drift, fixes don't propagate, and the same bug ends up debugged twice.

If you encounter an existing duplicated skill (the same skill present under both `claude/skills/` and `codex/skills/`), prefer to **consolidate** it into one canonical location before making further edits, and call this out to the user.

Use this canonical layout:

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

Do not author new skills under per-agent source trees such as `claude/skills/` or `codex/skills/`. Consolidate duplicated per-agent copies into the canonical location before making substantive edits.

### 2. Sync standalone skills to both install directories

Every change to a standalone canonical skill under `skills/` must be propagated to **both** agent install directories in the same flow:

- `~/.codex/skills/<skill-name>/`
- `~/.claude/skills/<skill-name>/`

Use the repo-level sync script; do not add per-skill `_sync.sh` wrappers:

```bash
python3 scripts/sync_skill.py push <skill-name>
python3 scripts/sync_skill.py pull <skill-name> claude|codex
```

Treat the sync as part of the edit — not a follow-up. If a change lands in the repo but only one install dir gets updated, the agents are now running different versions of the skill, which is exactly the situation the single-canonical-copy rule exists to prevent.

If an existing skill still lives under `claude/skills/` or `codex/skills/`, the same applies: the edit in the repo and the corresponding update under `~/.claude/skills/` or `~/.codex/skills/` must happen together.

Do not mirror plugin-packaged skills into direct install directories. A plugin skill should be available through its plugin install only; direct copies under `~/.codex/skills/<skill-name>/` or `~/.claude/skills/<skill-name>/` create duplicate skill triggers and must be removed.

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

### 3a. One canonical copy per specialized agent

Reusable specialized agents live under the repo-level `agents/` directory, not inside a skill folder. A skill may name an agent it wants the harness to spawn, but the agent remains globally reusable and must not be treated as owned by that skill.

The canonical native-agent layout is:

```
agents/
├── manifest.toml          # one manifest for all reusable specialized agents
├── code-mapper.md         # portable role prompt / domain contract
├── code-reviewer.md
└── ...
```

Do not hand-maintain separate Codex and Claude Code agent definitions. Update the canonical Markdown prompt and `agents/manifest.toml`, then run:

```bash
python3 scripts/sync_native_agents.py push
python3 scripts/sync_native_agents.py check
```

`sync_native_agents.py` renders harness-native files into:

- `~/.codex/agents/<agent-id>.toml`
- `~/.claude/agents/<agent-id>.md`

`agents/manifest.toml` owns harness-specific delivery metadata such as model, reasoning effort, sandbox/permission mode, tool restrictions, display color, and optional preloaded skills. Keep role prompts portable and put harness-specific fields in the manifest.

When a skill change relies on a subset of specialized agents, tag those manifest entries with that skill's group name. `scripts/sync_skill.py push <skill-name>` pushes the skill and then syncs native agents in the matching group.

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
- Do not refresh plugin skills into `~/.codex/skills/`; use the plugin install as the only runtime source.

For Claude Code availability:

- Keep `plugins/<plugin-name>/.claude-plugin/plugin.json` and `plugins/<plugin-name>/.claude-plugin/marketplace.json` in the plugin root.
- Validate the plugin before claiming it is installable.
- Refresh the durable local plugin copy, usually `~/plugins/<plugin-name>/`.
- Add or update the Claude marketplace source that contains `.claude-plugin/marketplace.json`, then install or update the plugin from that marketplace.
- Do not refresh plugin skills into `~/.claude/skills/`; use the plugin install as the only runtime source.

For standalone direct skill install directories, copy the canonical skill folder exactly, including scripts, references, tests, and thin `agents/` metadata if present. Do not hand-edit the installed copy and then forget to pull it back into the repo.

Useful local refresh commands for the current plugin convention:

```bash
rsync -a --delete plugins/<plugin-name>/ "$HOME/plugins/<plugin-name>/"

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

### 6a. Procedural and ability skills

Classify each skill as one of two categories:

- **Procedural skills** are manually invoked workflows. They define a workflow the agent should closely follow after explicit invocation. They may directly name other skills or native agents when the workflow intentionally delegates, spawns, or hands off work. Mark them in `SKILL.md` frontmatter with `disable-model-invocation: true` and:

  ```yaml
  metadata:
    ai-skills-category: procedural
    ai-skills-invocation: manual
  ```

- **Ability skills** are small, generic capabilities meant to be picked up automatically when context demands them. Their descriptions should be trigger-oriented, and they must not directly name other skills or native agents to invoke or delegate to. They should describe the needed capability and let the active harness choose the concrete mechanism.

Procedural skills must keep descriptions short and non-triggering so they do not compete with ability skills. Ability skills remain responsible for automatic discovery and trigger coverage.

### 7. Trigger scenarios for ability skill changes

Every new ability skill and every update to an existing ability skill must add or update trigger coverage in `tests/skill-trigger/scenarios.toml`. The scenario should capture the real user phrasing, repository context, provider/tool context, or failure mode that should make the skill get picked up.

Do not treat trigger testing as optional documentation for ability skills. If an ability skill's `description`, scope, or invocation behavior changes, update the trigger scenario registry in the same change.

Procedural skills do not have trigger scenarios. Prove their behavior with loaded-skill behavioral tests instead.

### 8. Run trigger tests before PR creation for ability skills

Before creating a PR for any ability skill addition or ability skill update, run the deterministic trigger contract and the behavioral trigger pressure suite:

```bash
python3 tests/skill-trigger/static_contract.py
SKILL_TRIGGER_AGENT_COMMAND='<command reading stdin>' \
  python3 tests/skill-trigger/trigger_harness.py
```

The behavioral command should use the target agent/runtime whose skill selection matters for the PR. If the behavioral suite cannot be run, do not silently proceed; report the exact blocker and get explicit user approval before creating the PR.

For procedural-only changes, still run the deterministic trigger contract to confirm procedural skills are excluded from trigger coverage, then run the relevant loaded-skill behavioral and contract suites.

### 9. Keep agent-driven test prompts neutral

Behavioral tests and any other agent-driven tests must not nudge the tested agent toward the expected answer. Actor-facing prompts may set test boundaries, such as no external tool calls, no file edits, no PR creation, response format, and the scenario facts. They must not include checklists of expected workflow steps, required conclusions, required agent names, or rubric items.

Treat actor-facing `prompt_instructions` like mocks or stubs in classic unit tests: they constrain unavailable side effects and injected facts, while assertions and judge criteria verify the behavior.

Put expected behavior in `[[scenario.criteria]]`, `judge_context`, deterministic assertions, or the test harness, not in actor-facing `prompt_instructions` or user prompts unless the user prompt is intentionally modeling real user wording. If a behavioral prompt tells the actor what it "must explain", "must mention", or "must state" about the behavior under test, treat that test as invalid and rewrite it before trusting the result.

### 10. Test positive behavior, not absence

Do not add or preserve tests whose assertion is that something is absent. This includes absent files, absent folders, absent generated artifacts, forbidden phrases, forbidden wording, or forbidden response text. Replace absence checks with positive assertions about expected behavior, structure, outcomes, state transitions, evidence, or lifecycle gates. When touching existing tests, remove absence checks from that test surface instead of carrying them forward.

---

# Rules for Writing Cross-Agent Skills

These rules apply when authoring a skill (instructions, recipes, or workflows) intended to run on more than one agent — Claude Code, Codex, Cursor, or any future agent. The goal is one source of truth, written at the right level of abstraction. **Maintain a single canonical skill; don't fork it per agent.**

## Core principle

The agent figures out the tools. The skill teaches the craft.

Keep the skill's center of gravity on the part that's actually hard — domain expertise, gotchas, output quality — and push agent-specific glue out to the thinnest possible edge.

Procedural skills are the exception for explicit workflow orchestration: they may name the exact skills or native agents they expect to invoke, delegate to, or spawn. Ability skills must stay portable and capability-oriented.

## Rules

### 1. Separate domain knowledge from the delivery layer

Every skill contains two kinds of content:

- **Domain knowledge** — how to produce a good X. What library to use, what the output should look like, what pitfalls to avoid, what good looks like. This is portable across every agent.
- **Delivery layer** — how to invoke the agent's tools. Tool names, file paths, prompt syntax. This is the fragile part.

Spend your effort on domain knowledge. Keep the delivery layer minimal and replaceable.

### 2. Write at the level of intent, not tool names

For ability skills, describe what to do, not which tool to call.

- ❌ "Use the `Read` tool to open the file."
- ✅ "Open and inspect the file."
- ❌ "Call `ask_user_input_v0` to get their preferences."
- ✅ "Ask the user about their preferences before proceeding."
- ❌ "Use `str_replace` to update the import statement."
- ✅ "Update the import statement in place."

Any reasonable agent maps intent to its native capability. This also future-proofs against tool renames within a single agent.

For procedural skills, direct skill or native-agent names are allowed when they are part of the workflow contract. Keep those references intentional and limited to orchestration points.

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

In ability skills, name the category, not the specific product or tool:

- ❌ "Open Chrome DevTools and inspect the network tab."
- ✅ "Inspect the page's network requests."
- ❌ "Run `pytest` to verify the changes."
- ✅ "Run the project's test suite to verify the changes." (then check `package.json`, `pyproject.toml`, etc.)

In procedural skills, product, skill, or agent names may appear when the workflow intentionally requires that named handoff or integration.

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

- [ ] No specific tool names from any agent appear in ability-skill prose (`Read`, `Write`, `Edit`, `str_replace`, `ask_user_input_v0`, etc.); procedural skills only name skills or native agents at intentional workflow orchestration points.
- [ ] Non-trivial logic lives in scripts under the skill folder, not in the prose.
- [ ] Every capability that might not exist (screenshots, browser, network, MCP) has a fallback chain.
- [ ] Required capabilities are declared at the top.
- [ ] The skill has been run end-to-end on at least one target agent.
- [ ] Ability skill trigger scenarios were added or updated in `tests/skill-trigger/scenarios.toml`; procedural skills have no trigger scenarios.
- [ ] The static trigger contract passed.
- [ ] For ability skills, the behavioral trigger pressure suite passed for the target agent/runtime, or the user explicitly approved the documented blocker before PR creation.
- [ ] No copy of this skill exists for a different agent. (If it does, merge them.)
- [ ] Adapter files, if any, are under ~30 lines each.
- [ ] Standalone skill changes have been synced to both direct skill install dirs; plugin-packaged skill changes have been refreshed through the plugin install only, with no duplicate direct skill copies.

## Anti-patterns to refuse

If asked to do any of the following while authoring a skill, push back:

- "Just make a Claude Code version and a Cursor version." → Propose one skill with thin adapters or fallback chains.
- "Hardcode the tool name, it's faster." → Cheaper today, more expensive next month. Use intent language.
- "Skip the fallback, this agent always has X." → Capabilities get removed, renamed, or rate-limited. Always provide a fallback for non-core capabilities.
- "Put the logic in the prose so the agent reasons through it each time." → Move deterministic logic to a script. The model is not where reliability lives.
