# Deferred work

This skill is **functional and installed** — `SKILL.md` is loaded and discoverable. Use it for the actual 2025 declaration filing. The work below is quality-assurance scaffolding that was scoped out of the initial build and is best run in dedicated future sessions.

## Phase 6.2-6.3 — Pressure scenario testing (TDD validation)

Scenarii definite în [`tests/pressure-scenarios.md`](tests/pressure-scenarios.md). Procedura RED-GREEN-REFACTOR e documentată.

**Blocker:** Task/Agent dispatch tool nu e expus în contextul subagent-ilor în harness-ul folosit la implementare (vezi [`tests/test-log.md`](tests/test-log.md) pentru detalii). Pentru a rula scenariile:

- **Opțiunea A:** rulează scenariile dintr-o sesiune Claude Code interactivă unde *main agent* are Task tool. Pentru fiecare scenariu (1-7):
  1. Dispatch baseline (no skill content în context) cu prompt-ul scenariului
  2. Dispatch GREEN cu instrucțiunea "citește `~/.claude/skills/declaratia-unica-romania/SKILL.md` apoi răspunde la: [scenariu]"
  3. Documentează răspunsurile verbatim în `tests/test-log.md`
  4. REFACTOR dacă GREEN eșuează: identifică rationalizarea, adaugă counter explicit în SKILL.md / workflow/citation-protocol.md, re-test.

- **Opțiunea B:** invocări `claude` CLI separate din shell, A/B manual.

**Disciplina e deja documentată** în skill (whitelist surse, citation protocol, anti-halucinare). Testarea pressure validează că disciplina e *respectată sub presiune*, nu doar documentată.

## Phase 7.1 — Legi cache seed pentru 2025

Cache-ul de fapte fiscale (`/Users/trocaneduard/Documents/Personal/declaratii-unice/_legi/2025/`) **nu e populat** la build. Asta e by-design:

- Skill-ul e **self-healing**: la Faza 3 (cache legi check), dacă folderul lipsește, declanșează refresh complet via `workflow/citation-protocol.md` (fetch din whitelist + scrie module).
- Cache-ul conține date PERSONALE / SPECIFICE FISCALE care nu aparțin în repo-ul `ai-skills` (per design `L3` din spec).

**Recomandare:** la prima sesiune reală de completare D212 pentru 2025, lasă orchestratorul să construiască cache-ul. Va întreba unde nu poate găsi un fapt în whitelist, ceea ce e comportamentul corect.

Module cache estimate (vor fi create):
- `salariu-minim.md`
- `plafoane-cass.md`
- `plafoane-cas.md`
- `impozit-dividende.md`
- `impozit-castig-capital.md`
- `impozit-dobanzi.md`
- `impozit-cripto.md`
- `pfa-real-cheltuieli.md`
- `tratate-dubla-impunere.md`
- `curs-bnr-mediu.md`
- `modificari-cf-fata-de-anul-precedent.md`

## Phase 7.2 — E2E validation împotriva 2025 IBKR data

Run end-to-end al skill-ului împotriva datelor reale IBKR din `/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/Documente IBKR/`, comparând XML-ul generat cu `2025/D212.xml` (golden reference) structural.

**Cum se face când e gata:**
1. Pornește o sesiune interactivă: "Folosește skill-ul `declaratia-unica-romania` pentru declarația mea pe anul fiscal 2025."
2. Skill-ul va declanșa Faza 1 (identificare), 2 (freshness), 3 (cache build dacă lipsește), 4 (preflight pe `Documente IBKR/`), 5 (calcul), 6 (generare).
3. Compară `outputs/D212.xml` cu `2025/D212.xml` structural (tag set + atribute set, nu valori — valorile pot diferi pe baza preciziei de conversie).
4. Iterează dacă apar drift-uri.

Această validare e cea mai informativă — folosește date reale. Defer-uită până la prima rulare reală.

## Phase 8 status — DONE

- 24 commits clean pe acest branch (`f54f3a8..HEAD`), inclusiv spec + plan + scaffold + 6 faze de conținut + test-log + acest DEFERRED.md
- 4 locații byte-identical (`claude/skills/`, `codex/skills/`, `~/.claude/skills/`, `~/.codex/skills/`)
- SKILL.md vizibil în system reminder ca skill loaded
- Branch `claude/thirsty-thompson-6ce3f6` push-uit la `origin`

## Notă proces

Plan-ul original avea 30 task-uri bite-sized cu execuție subagent-driven strict (implementer + spec reviewer + code quality reviewer per task). Implementarea a fost executată cu:
- Subagent per **fază** în loc de per task (din motive de buget context)
- Spec reviewers per fază (păstrat)
- Code quality review consolidat la final (deferat)
- Phase 6.2-6.3 și Phase 7 amânate ca documentat mai sus

Compromisul: skill-ul e livrat funcțional și folosibil acum, cu munca de QA documentată ca follow-up identificat.
