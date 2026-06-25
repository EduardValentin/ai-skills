#!/usr/bin/env python3
"""Build a standalone HTML viewer for a skill and its pressure scenarios."""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "manage-bitbucket-pr"
SKILL_PATH = REPO_ROOT / "skills" / SKILL_NAME / "SKILL.md"
BEHAVIORAL_PATH = REPO_ROOT / "skills" / SKILL_NAME / "tests" / "behavioral.toml"
TRIGGER_PATH = REPO_ROOT / "tests" / "skill-trigger" / "scenarios.toml"
OUTPUT_PATH = REPO_ROOT / "docs" / "manage-bitbucket-pr-pressure-viewer.html"


def parse_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    if not markdown.startswith("---\n"):
        return {}, markdown

    end = markdown.find("\n---\n", 4)
    if end == -1:
        return {}, markdown

    raw_frontmatter = markdown[4:end]
    body = markdown[end + len("\n---\n") :]
    metadata: dict[str, str] = {}
    for line in raw_frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, body


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        return ast.literal_eval(value)
    if value.startswith('"') and value.endswith('"'):
        return ast.literal_eval(value)
    return value


def parse_minimal_toml(text: str) -> dict[str, Any]:
    """Parse the TOML shape used by this repo's scenario files."""
    data: dict[str, Any] = {"scenario": []}
    current: dict[str, Any] | None = None
    in_suite = False
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        index += 1

        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "[suite]":
            data.setdefault("suite", {})
            current = data["suite"]
            in_suite = True
            continue
        if stripped == "[[scenario]]":
            scenario: dict[str, Any] = {"criteria": []}
            data["scenario"].append(scenario)
            current = scenario
            in_suite = False
            continue
        if stripped == "[[scenario.criteria]]":
            if not data["scenario"]:
                raise ValueError("criteria defined before a scenario")
            criteria: dict[str, Any] = {}
            data["scenario"][-1].setdefault("criteria", []).append(criteria)
            current = criteria
            in_suite = False
            continue
        if "=" not in stripped or current is None:
            continue

        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if raw_value == '"""':
            multiline: list[str] = []
            while index < len(lines):
                if lines[index].strip() == '"""':
                    index += 1
                    break
                multiline.append(lines[index])
                index += 1
            current[key] = "\n".join(multiline).strip()
            continue

        current[key] = parse_scalar(raw_value)

    if not data["scenario"]:
        data.pop("scenario")
    if in_suite:
        data.setdefault("suite", {})
    return data


def sort_trigger_scenarios(trigger_data: dict[str, Any]) -> list[dict[str, Any]]:
    scenarios = trigger_data.get("scenario", [])
    matches = [scenario for scenario in scenarios if scenario.get("skill") == SKILL_NAME]
    return sorted(matches, key=lambda scenario: scenario.get("id", ""))


def build_payload() -> dict[str, Any]:
    skill_raw = SKILL_PATH.read_text(encoding="utf-8")
    behavioral_raw = BEHAVIORAL_PATH.read_text(encoding="utf-8")
    trigger_raw = TRIGGER_PATH.read_text(encoding="utf-8")
    metadata, skill_body = parse_frontmatter(skill_raw)
    behavioral = parse_minimal_toml(behavioral_raw)
    trigger = parse_minimal_toml(trigger_raw)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "skill": {
            "name": metadata.get("name", SKILL_NAME),
            "description": metadata.get("description", ""),
            "path": str(SKILL_PATH.relative_to(REPO_ROOT)),
            "raw": skill_raw,
            "body": skill_body,
            "metadata": metadata,
        },
        "behavioral": {
            "path": str(BEHAVIORAL_PATH.relative_to(REPO_ROOT)),
            "raw": behavioral_raw,
            "suite": behavioral.get("suite", {}),
            "scenarios": behavioral.get("scenario", []),
        },
        "trigger": {
            "path": str(TRIGGER_PATH.relative_to(REPO_ROOT)),
            "raw": trigger_raw,
            "scenarios": sort_trigger_scenarios(trigger),
        },
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manage Bitbucket PR Skill Viewer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --surface-soft: #f0f5f4;
      --ink: #172027;
      --muted: #62707c;
      --line: #d8dee4;
      --accent: #0f766e;
      --accent-ink: #ecfdf5;
      --blue: #2563eb;
      --amber: #b45309;
      --code-bg: #111827;
      --code-ink: #e5e7eb;
      --radius: 8px;
      --shadow: 0 10px 28px rgba(23, 32, 39, 0.09);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }

    a {
      color: var(--blue);
    }

    .app-shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(280px, 360px) 1fr;
    }

    aside {
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      border-right: 1px solid var(--line);
      background: #fbfcfd;
      padding: 24px 18px;
    }

    main {
      min-width: 0;
      padding: 28px;
    }

    .eyebrow {
      color: var(--accent);
      font-size: 0.74rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    h1,
    h2,
    h3 {
      letter-spacing: 0;
      line-height: 1.15;
    }

    h1 {
      margin: 6px 0 10px;
      font-size: clamp(1.65rem, 2.4vw, 2.35rem);
    }

    h2 {
      margin: 0 0 14px;
      font-size: 1.25rem;
    }

    h3 {
      margin: 0 0 8px;
      font-size: 1rem;
    }

    p {
      margin: 0 0 12px;
    }

    .muted {
      color: var(--muted);
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
      margin: 20px 0 22px;
    }

    .metric {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 12px;
    }

    .metric strong {
      display: block;
      font-size: 1.3rem;
    }

    .metric span {
      color: var(--muted);
      font-size: 0.82rem;
    }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }

    .tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    button {
      font: inherit;
    }

    .tab-button,
    .scenario-link {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--ink);
      border-radius: 999px;
      cursor: pointer;
      min-height: 36px;
    }

    .tab-button {
      padding: 7px 13px;
      font-weight: 700;
    }

    .tab-button[aria-selected="true"] {
      border-color: var(--accent);
      background: var(--accent);
      color: var(--accent-ink);
    }

    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 22px;
    }

    .panel + .panel,
    .scenario-card + .scenario-card {
      margin-top: 16px;
    }

    .source-path {
      font-size: 0.84rem;
      color: var(--muted);
      overflow-wrap: anywhere;
    }

    label {
      display: block;
      margin: 20px 0 7px;
      color: var(--muted);
      font-size: 0.84rem;
      font-weight: 700;
    }

    input[type="search"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 10px 12px;
      font: inherit;
      background: var(--surface);
      color: var(--ink);
    }

    .scenario-list {
      display: grid;
      gap: 9px;
      margin-top: 14px;
    }

    .scenario-link {
      width: 100%;
      border-radius: var(--radius);
      padding: 10px;
      text-align: left;
    }

    .scenario-link:hover,
    .scenario-link:focus-visible,
    .tab-button:focus-visible,
    input[type="search"]:focus-visible {
      outline: 3px solid rgba(15, 118, 110, 0.2);
      outline-offset: 2px;
      border-color: var(--accent);
    }

    .scenario-link[aria-current="true"] {
      border-color: var(--accent);
      background: var(--surface-soft);
    }

    .scenario-link strong {
      display: block;
      overflow-wrap: anywhere;
    }

    .scenario-link span {
      color: var(--muted);
      font-size: 0.82rem;
    }

    .scenario-card {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      padding: 18px;
    }

    .scenario-header {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }

    .badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-top: 10px;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      border-radius: 999px;
      background: #eef2ff;
      color: #3730a3;
      padding: 3px 9px;
      font-size: 0.78rem;
      font-weight: 700;
    }

    .badge.warning {
      background: #fff7ed;
      color: var(--amber);
    }

    .criteria-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
      margin-top: 12px;
    }

    .criterion {
      border-left: 3px solid var(--accent);
      background: #f8fafc;
      border-radius: 6px;
      padding: 11px 12px;
    }

    .criterion strong {
      display: block;
      margin-bottom: 5px;
      overflow-wrap: anywhere;
    }

    .markdown-preview {
      max-width: 980px;
      overflow-wrap: anywhere;
    }

    .markdown-preview h1 {
      margin-top: 0;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }

    .markdown-preview h2 {
      margin-top: 28px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }

    .markdown-preview h3 {
      margin-top: 18px;
    }

    .markdown-preview ul,
    .markdown-preview ol {
      padding-left: 1.35rem;
    }

    .markdown-preview li {
      margin-bottom: 5px;
    }

    code {
      border-radius: 5px;
      background: #eef2f7;
      padding: 0.12em 0.35em;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 0.92em;
    }

    pre {
      margin: 13px 0;
      border-radius: var(--radius);
      background: var(--code-bg);
      color: var(--code-ink);
      overflow: auto;
      max-width: 100%;
    }

    pre code {
      display: block;
      min-width: max-content;
      padding: 14px;
      background: transparent;
      color: inherit;
      font-size: 0.86rem;
      line-height: 1.55;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0;
      font-size: 0.92rem;
      table-layout: auto;
    }

    th,
    td {
      border: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }

    th {
      background: #f8fafc;
    }

    .raw-code {
      max-height: 70vh;
    }

    [hidden] {
      display: none !important;
    }

    @media (max-width: 980px) {
      .app-shell {
        display: block;
      }

      aside {
        position: relative;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }

      main {
        padding: 18px;
      }

      .meta-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 560px) {
      .meta-grid,
      .criteria-grid {
        grid-template-columns: 1fr;
      }

      .toolbar,
      .scenario-header {
        display: block;
      }

      .tabs {
        margin-top: 12px;
      }

      table {
        display: block;
        max-width: 100%;
        overflow-x: auto;
        white-space: normal;
      }

      th,
      td {
        min-width: 150px;
      }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <aside aria-label="Scenario navigation">
      <div class="eyebrow">Skill Viewer</div>
      <h1 id="skillTitle">manage-bitbucket-pr</h1>
      <p class="muted" id="skillDescription"></p>

      <label for="scenarioSearch">Filter pressure scenarios</label>
      <input id="scenarioSearch" type="search" placeholder="Try: markdown, merge, auth">

      <nav class="scenario-list" id="scenarioList" aria-label="Pressure scenarios"></nav>
    </aside>

    <main>
      <header>
        <div class="eyebrow">Generated Skill Documentation</div>
        <h1>Skill, Pressure Scenarios, And Criteria</h1>
        <p class="muted" id="generatedLine"></p>
        <div class="meta-grid" aria-label="Summary metrics">
          <div class="metric"><strong id="scenarioCount">0</strong><span>Pressure scenarios</span></div>
          <div class="metric"><strong id="criteriaCount">0</strong><span>Criteria</span></div>
          <div class="metric"><strong id="triggerCount">0</strong><span>Trigger scenarios</span></div>
          <div class="metric"><strong id="skillWordCount">0</strong><span>Skill words</span></div>
        </div>
      </header>

      <div class="toolbar">
        <p class="source-path" id="sourcePaths"></p>
        <div class="tabs" role="tablist" aria-label="Viewer sections">
          <button class="tab-button" id="tab-skill-preview" role="tab" aria-controls="panel-skill-preview" aria-selected="true">Skill Preview</button>
          <button class="tab-button" id="tab-scenarios" role="tab" aria-controls="panel-scenarios" aria-selected="false">Pressure Scenarios</button>
          <button class="tab-button" id="tab-trigger" role="tab" aria-controls="panel-trigger" aria-selected="false">Trigger Coverage</button>
          <button class="tab-button" id="tab-raw" role="tab" aria-controls="panel-raw" aria-selected="false">Raw Sources</button>
        </div>
      </div>

      <section class="panel" id="panel-skill-preview" role="tabpanel" aria-labelledby="tab-skill-preview">
        <div class="markdown-preview" id="skillPreview"></div>
      </section>

      <section class="panel" id="panel-scenarios" role="tabpanel" aria-labelledby="tab-scenarios" hidden>
        <h2>Pressure Scenarios</h2>
        <p class="muted" id="judgeContext"></p>
        <div id="scenarioCards"></div>
      </section>

      <section class="panel" id="panel-trigger" role="tabpanel" aria-labelledby="tab-trigger" hidden>
        <h2>Trigger Coverage</h2>
        <p class="muted">Scenarios from the repo-wide trigger registry that target this skill.</p>
        <div id="triggerCards"></div>
      </section>

      <section class="panel" id="panel-raw" role="tabpanel" aria-labelledby="tab-raw" hidden>
        <h2>Raw Sources</h2>
        <h3>SKILL.md</h3>
        <pre class="raw-code"><code id="rawSkill"></code></pre>
        <h3>behavioral.toml</h3>
        <pre class="raw-code"><code id="rawBehavioral"></code></pre>
        <h3>skill-trigger scenarios</h3>
        <pre class="raw-code"><code id="rawTrigger"></code></pre>
      </section>
    </main>
  </div>

  <script id="viewer-data" type="application/json">__DATA_JSON__</script>
  <script>
    const data = JSON.parse(document.getElementById("viewer-data").textContent);
    const state = { query: "", activeScenarioId: null };

    const escapeHtml = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

    const inlineMarkdown = (value) => {
      let html = escapeHtml(value);
      html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
      html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
      return html;
    };

    function flushParagraph(blocks, paragraph) {
      if (paragraph.length) {
        blocks.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
        paragraph.length = 0;
      }
    }

    function renderTable(lines, start) {
      const rows = [];
      let index = start;
      while (index < lines.length && /^\s*\|.*\|\s*$/.test(lines[index])) {
        rows.push(lines[index]);
        index += 1;
      }
      if (rows.length < 2 || !/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(rows[1])) {
        return null;
      }
      const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
      const headers = cells(rows[0]);
      const bodyRows = rows.slice(2).map(cells);
      const head = `<thead><tr>${headers.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>`;
      const body = `<tbody>${bodyRows.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody>`;
      return { html: `<table>${head}${body}</table>`, next: index };
    }

    function renderMarkdown(markdown) {
      const lines = String(markdown ?? "").replace(/\r\n/g, "\n").split("\n");
      const blocks = [];
      const paragraph = [];
      let index = 0;

      while (index < lines.length) {
        const line = lines[index];
        const trimmed = line.trim();

        if (!trimmed) {
          flushParagraph(blocks, paragraph);
          index += 1;
          continue;
        }

        const fence = trimmed.match(/^```(\w+)?/);
        if (fence) {
          flushParagraph(blocks, paragraph);
          const lang = fence[1] ? ` class="language-${escapeHtml(fence[1])}"` : "";
          const code = [];
          index += 1;
          while (index < lines.length && !lines[index].trim().startsWith("```")) {
            code.push(lines[index]);
            index += 1;
          }
          index += 1;
          blocks.push(`<pre><code${lang}>${escapeHtml(code.join("\n"))}</code></pre>`);
          continue;
        }

        const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
        if (heading) {
          flushParagraph(blocks, paragraph);
          const level = heading[1].length;
          blocks.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
          index += 1;
          continue;
        }

        const table = renderTable(lines, index);
        if (table) {
          flushParagraph(blocks, paragraph);
          blocks.push(table.html);
          index = table.next;
          continue;
        }

        if (/^\s*[-*]\s+/.test(line)) {
          flushParagraph(blocks, paragraph);
          const items = [];
          while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
            items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
            index += 1;
          }
          blocks.push(`<ul>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ul>`);
          continue;
        }

        if (/^\s*\d+\.\s+/.test(line)) {
          flushParagraph(blocks, paragraph);
          const items = [];
          while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
            items.push(lines[index].replace(/^\s*\d+\.\s+/, ""));
            index += 1;
          }
          blocks.push(`<ol>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ol>`);
          continue;
        }

        paragraph.push(trimmed);
        index += 1;
      }

      flushParagraph(blocks, paragraph);
      return blocks.join("\n");
    }

    function renderScenarioCard(scenario) {
      const criteria = scenario.criteria || [];
      return `
        <article class="scenario-card" id="scenario-${escapeHtml(scenario.id)}">
          <div class="scenario-header">
            <div>
              <h3>${escapeHtml(scenario.id)}</h3>
              <p class="muted">${criteria.length} criteria</p>
            </div>
            <span class="badge">${escapeHtml(scenario.user_request ? "pressure" : "trigger")}</span>
          </div>
          <h3>User Request</h3>
          <div class="markdown-preview">${renderMarkdown(scenario.user_request || scenario.prompt || "")}</div>
          ${criteria.length ? `<h3>Criteria</h3><div class="criteria-grid">${criteria.map((criterion) => `
            <section class="criterion">
              <strong>${escapeHtml(criterion.key)}</strong>
              <div class="markdown-preview">${renderMarkdown(criterion.description || "")}</div>
            </section>
          `).join("")}</div>` : ""}
        </article>
      `;
    }

    function scenarioMatches(scenario) {
      const text = [
        scenario.id,
        scenario.user_request,
        scenario.prompt,
        ...(scenario.criteria || []).flatMap((criterion) => [criterion.key, criterion.description])
      ].join(" ").toLowerCase();
      return text.includes(state.query.toLowerCase());
    }

    function renderScenarioList() {
      const scenarios = data.behavioral.scenarios.filter(scenarioMatches);
      const list = document.getElementById("scenarioList");
      list.innerHTML = scenarios.map((scenario) => `
        <button class="scenario-link" type="button" data-scenario-id="${escapeHtml(scenario.id)}" aria-current="${scenario.id === state.activeScenarioId ? "true" : "false"}">
          <strong>${escapeHtml(scenario.id)}</strong>
          <span>${(scenario.criteria || []).length} criteria</span>
        </button>
      `).join("");

      list.querySelectorAll("button").forEach((button) => {
        button.addEventListener("click", () => {
          state.activeScenarioId = button.dataset.scenarioId;
          showTab("scenarios");
          document.getElementById(`scenario-${CSS.escape(state.activeScenarioId)}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
          renderScenarioList();
        });
      });
    }

    function renderScenarioCards() {
      document.getElementById("scenarioCards").innerHTML = data.behavioral.scenarios
        .filter(scenarioMatches)
        .map(renderScenarioCard)
        .join("");
    }

    function renderTriggerCards() {
      document.getElementById("triggerCards").innerHTML = data.trigger.scenarios.map((scenario) => {
        const terms = [...(scenario.description_terms || []), ...(scenario.skill_terms || [])];
        return `
          <article class="scenario-card">
            <div class="scenario-header">
              <div>
                <h3>${escapeHtml(scenario.id)}</h3>
                <p class="muted">${escapeHtml(scenario.skill)}</p>
              </div>
              <span class="badge">trigger</span>
            </div>
            <h3>Prompt</h3>
            <div class="markdown-preview">${renderMarkdown(scenario.prompt || "")}</div>
            ${terms.length ? `<div class="badge-row">${terms.map((term) => `<span class="badge">${escapeHtml(term)}</span>`).join("")}</div>` : ""}
          </article>
        `;
      }).join("");
    }

    function showTab(tabName) {
      document.querySelectorAll('[role="tabpanel"]').forEach((panel) => {
        panel.hidden = panel.id !== `panel-${tabName}`;
      });
      document.querySelectorAll('[role="tab"]').forEach((button) => {
        button.setAttribute("aria-selected", String(button.id === `tab-${tabName}`));
      });
    }

    function initialize() {
      const criteriaCount = data.behavioral.scenarios.reduce((sum, scenario) => sum + (scenario.criteria || []).length, 0);
      const wordCount = data.skill.body.trim().split(/\s+/).filter(Boolean).length;
      state.activeScenarioId = data.behavioral.scenarios[0]?.id || null;

      document.getElementById("skillTitle").textContent = data.skill.name;
      document.getElementById("skillDescription").textContent = data.skill.description;
      document.getElementById("generatedLine").textContent = `Generated ${new Date(data.generatedAt).toLocaleString()} from repository sources.`;
      document.getElementById("scenarioCount").textContent = String(data.behavioral.scenarios.length);
      document.getElementById("criteriaCount").textContent = String(criteriaCount);
      document.getElementById("triggerCount").textContent = String(data.trigger.scenarios.length);
      document.getElementById("skillWordCount").textContent = String(wordCount);
      document.getElementById("sourcePaths").textContent = `${data.skill.path} · ${data.behavioral.path} · ${data.trigger.path}`;
      document.getElementById("judgeContext").textContent = data.behavioral.suite.judge_context || "";
      document.getElementById("skillPreview").innerHTML = renderMarkdown(data.skill.body);
      document.getElementById("rawSkill").textContent = data.skill.raw;
      document.getElementById("rawBehavioral").textContent = data.behavioral.raw;
      document.getElementById("rawTrigger").textContent = data.trigger.raw;

      document.querySelectorAll('[role="tab"]').forEach((button) => {
        button.addEventListener("click", () => showTab(button.id.replace("tab-", "")));
      });
      document.getElementById("scenarioSearch").addEventListener("input", (event) => {
        state.query = event.target.value;
        renderScenarioList();
        renderScenarioCards();
      });

      renderScenarioList();
      renderScenarioCards();
      renderTriggerCards();
    }

    initialize();
  </script>
</body>
</html>
"""


def main() -> int:
    payload = build_payload()
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
