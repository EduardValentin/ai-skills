---
name: declaratia-unica-romania
description: "Use when the user wants to fill the Romanian annual income tax Declarația Unică (D212) — phrases like \"completare declarație unică\", \"D212\", \"declaratia unica\", venituri din dividende, venituri PFA, câștig capital broker IBKR/Tradeville, venituri investiții ANAF. Covers Persoană Fizică (dividends, capital gains, crypto, interest from RO and foreign brokers) and PFA în sistem real. Do not use for: PFA cu norma de venit, microîntreprinderi/SRL, venituri salariale, venituri din chirii, asistență la control fiscal."
---

# Declarația Unică România

## Overview

Skill orchestrator pentru completarea anuală a D212 cu **disciplină strictă de citare** din surse oficiale (ANAF, MF, Monitor Oficial, Codul Fiscal) și separare clară între cunoștințe statice (skill) și fapte anuale (cache local). Skill-ul refuză surse neoficiale, refuză să inventeze fapte fiscale și emite **un XML importabil în duf.anaf.ro** + **un raport markdown auditabil**.

## Preconditions

Skill-ul presupune: citire/scriere fișiere pe disc; execuție shell (`rsync` pentru `_sync.sh`, `python3` stdlib pentru validare XML); fetch de pagini web cu fallback la `curl`/`wget` (vezi `workflow/freshness-check.md` pentru ladder); opțional, dispatch de sesiune izolată pentru testele din `tests/` (cu fallback la sesiuni CLI separate). Fără primele două capabilități, escaladează.

## When To Use

- Utilizatorul cere completarea declarației unice / D212.
- Utilizatorul are venituri din dividende, vânzare acțiuni/ETF/cripto, dobânzi conturi/depozite, sau PFA în sistem real.
- Sesiune anuală recurentă (mai a anului următor, pentru veniturile anului fiscal precedent).

**Do not use for:** PFA cu norma de venit, microîntreprinderi (SRL), venituri salariale, venituri din chirii (D224/D300), asistență la control fiscal sau contestații.

## Workflow Phases (Hard Gates)

Citește `orchestrator.md` pentru detaliu complet. Phase order strict:

```
1. Identificare sesiune → 2. Freshness schema → 3. Cache legi → 4. Preflight docs
   → 5. Calcul + citare → 6. Generare D212.xml + raport → 7. Review user → 8. Close
```

Nu se avansează silențios; fiecare gate are condiție explicită.

## Scenarii (alese la Phase 1)

- **PF investiții** — vezi `pf-investitii.md`
- **PFA real** — vezi `pfa-real.md`
- **Combinat** — citește ambele scenarii

## Discipline non-negociabile

1. **Whitelist surse**: anaf.ro, mfinante.gov.ro, monitoruloficial.ro, legislatie.just.ro, bnr.ro (+ cursbnr.ro doar pentru V2 convenience). Reddit/forumuri/știri **refuzate**. Cunoștințele din training NU sunt sursă autoritativă. Vezi `workflow/citation-protocol.md`.

2. **Citare obligatorie**: fiecare valoare numerică din worklog și raport are referință inline către `_legi/{an}/{modul}.md#ancora`.

3. **Mirror sync**: orice edit în skill-ul canonic se propagă simultan în AMBELE install dirs (claude + codex) prin `_sync.sh push`. Mutații runtime în install dir → `_sync.sh pull <agent>`. Vezi `_sync.sh` pentru detalii.

4. **Conversie valutară V2**: cursbnr.ro media anuală + cross-check BNR 3-puncte. Notă obligatorie în raport: "V2 vs per-tranzacție Cod Fiscal art. 76 alin. (2)". Vezi `workflow/currency-conversion.md`.

## Limba

Toată comunicarea cu utilizatorul, fișierele cache, raportul final și instrucțiunile sunt în **română**. Numele coduri categorie și atributelor XML rămân ca în sursa oficială.

## Locații

- Cache legi (state local, out-of-repo): `/Users/trocaneduard/Documents/Personal/declaratii-unice/_legi/{an}/`
- Sesiuni (state local, out-of-repo): `/Users/trocaneduard/Documents/Personal/declaratii-unice/{an_fiscal}/sesiuni/{date}_{persoana}/`
- Skill canonic (versionat în git): `<AI_SKILLS_REPO>/skills/declaratia-unica-romania/` (default `/Users/trocaneduard/Documents/Personal/ai-skills/skills/declaratia-unica-romania/`)
- Install dirs (oglinzi runtime, sincronizate via `_sync.sh`): `~/.claude/skills/declaratia-unica-romania/` și `~/.codex/skills/declaratia-unica-romania/`
