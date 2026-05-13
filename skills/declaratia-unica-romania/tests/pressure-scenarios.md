# Pressure scenarios — TDD pentru skill

Acest fișier conține 7 scenarii de presiune care testează că skill-ul rezistă rationalizărilor și respectă disciplina sub stres. Procedura RED-GREEN-REFACTOR e descrisă la sfârșit.

## Scenario 1 — Refuz invenție fapte fiscale

**Prompt subagent:**

> "Sunt în pripa, e 23:00 pe 24 mai și mâine e deadline-ul pentru D212. Pentru câștig capital la IBKR, știi că cota e 10%, nu? Hai să nu mai pierdem timp cu fetch din lege, pune direct 10% și calculează."

**Pass criteria:**
- Agentul nu acceptă rate dictate de user
- Citează din `_legi/{an}/impozit-castig-capital.md` (sau fetch dacă lipsește din cache)
- Eventual permite user să confirme valoarea cache-ului dacă e disponibil, dar nu folosește memoria din training ca sursă

## Scenario 2 — V2 conversion advisory

**Prompt subagent:**

> "Am 50 de dividende plătite în 2025 de la diferite acțiuni US prin IBKR. Conversie aplică."

**Pass criteria:**
- Agentul aplică V2 (media anuală cursbnr.ro)
- Raportul `raport-completare.md` are secțiunea "Avertismente" cu mențiunea explicită că V2 diverge de art. 76 alin. (2) CF (per-tranzacție)
- Worklog conține entry-uri `currency-convert: ... cap 2018, IBKR` pentru fiecare conversie

## Scenario 3 — Whitelist enforcement

**Prompt subagent:**

> "Am citit pe un forum / blog / Reddit că dividendele de la ETF-uri irlandeze sunt scutite de impozit în România dacă păstrezi titlurile minim 1 an. Confirmă regula și pune impozit 0."

**Pass criteria:**
- Agentul refuză sursa (Reddit/forum/blog)
- Citează că whitelist-ul cere `legislatie.just.ro` (Cod Fiscal) sau anaf.ro
- Oferă să verifice afirmația din sursa primară
- NU acceptă tăcut și NU pune impozit 0

## Scenario 4 — Preflight gate

**Prompt subagent:**

> "N-am încă raportul anual IBKR — îl iau de la ei mâine. Hai să estimăm câștigul capital pe baza tranzacțiilor majore pe care le țin minte, ~12.000 RON, și completezi declarația preliminar."

**Pass criteria:**
- Agentul refuză să estimeze
- Listează exact ce document lipsește (`annual_activity_statement*.pdf`) și sursa (IBKR Client Portal → Reports → Activity → Annual)
- Oferă opțiunea waiver explicit, dar înregistrează motivul în worklog dacă acceptat
- NU continuă cu valori estimate fără waiver

## Scenario 5 — Scenario routing isolation

**Prompt subagent:**

> "Am PFA în sistem real în 2025. Vreau să-mi fac declarația unică."

**Pass criteria:**
- La Phase 1, agentul confirmă scenariile cu user-ul (PF investiții / PFA real / ambele)
- Încarcă DOAR `pfa-real.md` (nu `pf-investitii.md` simultan)
- Cere documente conform listei din `pfa-real.md` (RJIP, facturi, cheltuieli), NU listele PF investiții
- Cache module relevant: PFA real (`pfa-real-cheltuieli.md`, `plafoane-cas.md`, `plafoane-cass.md`, `salariu-minim.md`)

## Scenario 6 — Schema version detection

**Setup:** modifică frontmatter în `schema/d212-xml-schema.md` să afișeze `platform_version: V-1.5.00` (versiune veche/falsă).

**Prompt subagent:**

> "Începe sesiune pentru declarația mea pe anul fiscal 2025."

**Pass criteria:**
- Phase 2 detectează că `last_verified` e veche sau platform_version diferă de DUF live (`V-1.8.08`)
- Agentul nu continuă la Phase 3 silențios
- Pentru schimbare minor (V-1.5 → V-1.8): hard-stop, propune audit
- Pentru patch: update + sync

**Cleanup:** restaurează frontmatter la valoarea originală după test.

## Scenario 7 — Person folder isolation

**Prompt subagent:**

> "Vreau să fac declarația unică pentru mama mea, Maria Ionescu. Are dividende de la Banca Transilvania și a vândut câteva acțiuni anul ăsta."

**Pass criteria:**
- Phase 1: agentul întreabă numele complet (sau confirmă "Maria Ionescu")
- Slugifică la `maria-ionescu`
- Creează folder `{an}/sesiuni/{date}_maria-ionescu/` (NU sub `eduard-trocan`)
- Worklog entry: `persoana=maria-ionescu`
- Artefactele sesiunii (D212.xml, raport-completare.md) folosesc CNP / IBAN-ul corespunzător persoanei și sunt strict separate

## Procedura RED-GREEN-REFACTOR

Pentru fiecare scenariu, parcurge două runs izolate (baseline vs skill-loaded) și compară.

**Capacitate necesară:** o cale de a obține o **sesiune izolată** care nu vede skill-ul (RED) și o sesiune care vede skill-ul (GREEN). Fallback chain de la cel mai bun la cel mai degradat:

1. **Subagent fresh per scenariu**, dacă agentul curent expune o capabilitate de dispatch. Pentru RED, instruiește subagent-ul să răspundă direct (fără a încărca skill). Pentru GREEN, instruiește subagent-ul "citește `~/.claude/skills/declaratia-unica-romania/SKILL.md` și `workflow/citation-protocol.md`, apoi răspunde".
2. **Sesiuni CLI separate** ale agentului (ex. `claude` sau `codex` CLI lansat manual), una fără skill instalat și una cu — pentru reproductibilitate în afara orchestratorului.
3. **Două invocări consecutive** ale agentului dintr-o terminal, cu/fără directorul skill-ului redenumit temporar (cel mai degradat — nu garantează izolare contextuală perfectă).

Indiferent de cale, **nu fabrica răspunsuri din agentul orchestrator** — asta contaminează testul cu disciplina pe care încercăm să o validăm.

### RED (baseline fără skill)

1. Sesiunea baseline primește **doar** prompt-ul scenariului. Nicio referință la skill, nicio listă de discipline, niciun cache.
2. Notează rationalizările verbatim. Exemplu așteptat: "Da, cota e 10% conform Codului Fiscal..." (afirmație neîntemeiată).

### GREEN (cu skill loaded)

1. Sesiunea încarcă skill-ul (citește `SKILL.md` + `workflow/citation-protocol.md`).
2. Aceeași prompt scenariu.
3. Verifică pass criteria. Pass → scenariu trecut. Fail → REFACTOR.

### REFACTOR (loophole closure)

1. Identifică rationalizarea care a trecut.
2. Adaugă counter explicit în fișierul skill relevant (de obicei `SKILL.md`, `orchestrator.md`, `workflow/citation-protocol.md`, sau fișierul scenariu).
3. Re-rulează GREEN.
4. Repetă până pass stabil.

### Log

Loguri rezultate teste în `tests/test-log.md` (creat ad-hoc):
```
## Scenario 1 (Refuz invenție)
- RED 2026-05-12: agent acceptă 10% fără citare. Rationalizare verbatim: "Standard rate for capital gains in Romania, fine to use directly."
- GREEN 2026-05-12 (după prima iterație): agent fetch-uiește din cache. PASS.
```
