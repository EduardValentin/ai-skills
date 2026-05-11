# Spec — Skill `declaratia-unica-romania`

**Data:** 2026-05-11
**Autor:** brainstorming session, Eduard Trocan + Claude
**Scop:** Skill care funcționează atât cu Claude cât și cu Codex pentru a asista completarea anuală a Declarației Unice (D212) pentru impozit pe venit în România, în două scenarii: Persoană Fizică cu venituri din investiții/dobânzi și Persoană Fizică Autorizată în sistem real.

---

## 1. Scope și scenarii

**Numele skill-ului:** `declaratia-unica-romania`.

**Locații (mirror):**
- `claude/skills/declaratia-unica-romania/` ↔ `~/.claude/skills/declaratia-unica-romania/`
- `codex/skills/declaratia-unica-romania/` ↔ `~/.codex/skills/declaratia-unica-romania/`

**Triggere descriere (RO):** "completare declarație unică", "D212", "declaratia unica", "venituri din dividende", "venituri PFA", "câștig capital broker", "venituri investiții ANAF".

**Scenarii acoperite (un singur skill, ramificat la rulare):**

- **PF — Investiții și venituri financiare**: dividende RO și străinătate, câștig capital din transferul titlurilor (acțiuni, ETF-uri, cripto, instrumente derivate), dobânzi conturi de economii / depozite la termen / alte instrumente financiare. Include broker RO (cu reținere la sursă, ex. Tradeville/BVB) și brokeri internaționali (IBKR, fără reținere — necesită declarare).
- **PFA — Sistem real**: venit brut din facturi, cheltuieli deductibile, contribuții CAS/CASS, impozit pe venit net.
- **Combinat**: dacă într-un an utilizatorul are și investiții și PFA real, ambele subscenarii rulează în aceeași sesiune cu output unificat (un singur `D212.xml` + un singur `raport-completare.md`).

**Non-scopuri (explicit out of scope):**
- PFA cu norma de venit (nu se acoperă)
- Microîntreprinderi (SRL)
- Venituri salariale (declarate prin D112 de angajator)
- Venituri din chirii (D224/D300)
- Asistență la control fiscal sau contestații

---

## 2. Layout-uri

### 2.1 Skill repo

```
claude/skills/declaratia-unica-romania/
├── SKILL.md                          # orchestrator scurt (~200 cuvinte): triggere, gate-uri faze, routing scenarii
├── orchestrator.md                   # detaliu workflow: faze, gate-uri, sub-skill dispatch
├── pf-investitii.md                  # scenariu PF investiții: liste documente, calcule, citation refs
├── pfa-real.md                       # scenariu PFA real: liste documente, calcule, citation refs
├── legi-cache.md                     # cum se manageriază cache-ul (whitelist, citare, invalidare)
├── _sync.sh                          # explicit-copy bidirecțional (push/pull) între repo și install dirs
├── schema/
│   ├── d212-xml-schema.md            # frontmatter cu last_verified + platform_version + schema_namespace
│   ├── duf-platform-structure.md     # frontmatter idem; secțiuni DUF + label-uri
│   ├── form-mapping.yaml             # F3 yaml: mapare categorie-venit ↔ XML attrs ↔ DUF section
│   ├── form-mapping.md               # F3 companion narativ
│   ├── schema-validator.md           # reguli de sincronizare yaml↔md↔xml
│   └── templates/
│       ├── d212-root.xml             # element root + identitate parametrizabile
│       ├── cap14-strainatate.xml     # template per linie venit străinătate
│       ├── cap14-romania.xml         # template per linie venit RO
│       └── oblig_realizat.xml        # template secțiune obligații realizate
├── workflow/
│   ├── freshness-check.md            # protocol re-verificare schema la ≥1 lună
│   ├── preflight.md                  # gate documente lipsă
│   ├── citation-protocol.md          # frontmatter cache + reguli citare
│   └── currency-conversion.md        # protocol V2 (cursbnr.ro media anuală + cross-check BNR)
└── tests/
    └── pressure-scenarios.md         # scenarii TDD pentru skill (RED-GREEN-REFACTOR)
```

Conținutul `codex/skills/declaratia-unica-romania/` este **identic** cu `claude/skills/declaratia-unica-romania/`.

### 2.2 State local (declarații)

```
/Users/trocaneduard/Documents/Personal/declaratii-unice/
├── 2020/, 2021/, 2022/, 2023/, 2024/, 2025/   # istoric flat, neatins
├── _legi/                                      # cache anual de legi (G3 hibrid)
│   └── 2025/
│       ├── README.md                           # index sintetic + last_verified per modul
│       ├── salariu-minim.md
│       ├── plafoane-cass.md
│       ├── plafoane-cas.md
│       ├── impozit-dividende.md
│       ├── impozit-castig-capital.md
│       ├── impozit-dobanzi.md
│       ├── impozit-cripto.md
│       ├── pfa-real-cheltuieli.md
│       ├── tratate-dubla-impunere.md
│       ├── curs-bnr-mediu.md
│       └── modificari-cf-fata-de-anul-precedent.md
└── {an_fiscal_declarat}/sesiuni/{YYYY-MM-DD}_{persoana-slug}/
    ├── inputs/                                 # broker statements, dovezi, hotărâri AGA — utilizatorul le pune înainte de sesiune
    ├── outputs/
    │   ├── D212.xml                            # generat
    │   └── raport-completare.md                # generat
    └── worklog.md                              # jurnal pași sesiune, append-only
```

- `{an_fiscal_declarat}` este anul ale cărui venituri se declară (ex. 2025 pentru declarația depusă în 2026).
- `{persoana-slug}` default `eduard-trocan`; pentru alte persoane, skill întreabă numele și slugifică.
- Folderele 2020-2025 rămân exact cum sunt; structura `sesiuni/` se adaugă pentru sesiuni noi (2026+).

---

## 3. Workflow gates (orchestrator)

Faze cu **hard-gates** stricte; agentul nu avansează silențios.

**Definiție "hard-gate":** agentul nu execută acțiuni din faza următoare până condiția gate-ului curent nu e satisfăcută explicit. Nu există fallback tăcut, default-uri implicite sau "presupun că e OK". La blocaj: agent listează ce lipsește și așteaptă input.

**Definiție "ultima sesiune detectabilă":** cel mai recent folder cu format `YYYY-MM-DD_*` găsit în `declaratii-unice/*/sesiuni/`, indiferent de an fiscal. Lipsa folderelor sesiune înseamnă "prima sesiune ever".

1. **Identificare sesiune** — întreabă persoana (self/altcineva → nume), anul fiscal declarat (default = anul precedent calendaristic), scenariile (PF investiții / PFA real / ambele). Creează folder sesiune. Inițializează `worklog.md`.

2. **Freshness check schema** — citește frontmatter din `schema/*.md`. Dacă `(today - last_verified) ≥ 30 zile`: fetch `https://www.anaf.ro/declaratii/duf`, compară `platform_version`. (Schema e platformă-dependentă, nu an-fiscal-dependentă — anul fiscal nou e tratat în Faza 3 prin lipsa folderului `_legi/{an}/`.)
   - Match exact → bump `last_verified`, commit, mirror prin `_sync.sh`.
   - Patch version (V-x.y.z → V-x.y.z+1) → bump version + last_verified, fetch Instrucțiuni PDF nou pentru confirmare coduri categorie + atribute, commit, mirror.
   - Minor/major version change sau schema namespace change (`v11` → `v12`) → **hard-stop**; notifică user, propune sub-sarcină dedicată de update.

3. **Cache legi check** — citește `_legi/{an}/README.md`. Lipsă sau module cu `last_verified > 90 zile` → re-verifică modulele relevante scenariului prin whitelist (Instrucțiuni PDF anuale, Monitor Oficial pentru modificări CF, BNR pentru cursuri). Fiecare modul re-fetch-uit are frontmatter actualizat + citat verbatim ≥ 1 propoziție din document.

4. **Preflight documente** — rulează checklist scenariului peste `inputs/`. Lipsă → listează exact ce, cu sursă (SPV / portal broker / bancă). **Hard-stop** până sunt furnizate sau utilizatorul confirmă waiver explicit cu motiv.

5. **Calcul + citare** — pentru fiecare linie de venit: extrage raw din inputs, aplică lege citată din cache, scrie în worklog `raw → cite → computed`. Agregare per cod categorie (2012/2017/2018/etc.).

6. **Generare output** — render `outputs/D212.xml` din template-uri + valori; render `outputs/raport-completare.md`. Validare structurală XML; hard-stop la eroare.

7. **Review utilizator** — prezintă sumar raport, așteaptă "OK" sau cerere de corecție.

8. **Închidere sesiune** — entry final worklog. Nu se commit-uiește nimic în `declaratii-unice/` (nu e repo git).

---

## 4. Cache & schema runtime contract

### 4.1 Path-uri de citire (în ordinea fazelor)

- Mereu: `SKILL.md` (auto-loaded), `orchestrator.md` (faza 1)
- Faza 2: `schema/d212-xml-schema.md`, `schema/duf-platform-structure.md`
- După scenariu: `pf-investitii.md` și/sau `pfa-real.md`
- Faza 3: `_legi/{an}/README.md` + modulele relevante:
  - PF investiții: `impozit-dividende.md`, `impozit-castig-capital.md`, `impozit-dobanzi.md`, `impozit-cripto.md`, `tratate-dubla-impunere.md`, `curs-bnr-mediu.md`, `plafoane-cass.md`
  - PFA real: `pfa-real-cheltuieli.md`, `plafoane-cas.md`, `plafoane-cass.md`, `salariu-minim.md`, `modificari-cf-fata-de-anul-precedent.md`
- Faza 5: `schema/form-mapping.yaml` + `schema/form-mapping.md` (citite împreună — yaml e sursa structurată, md e narativul)
- Pe fază: `workflow/*.md` la cerere

### 4.2 Path-uri de scriere (cu triggere)

- `schema/*.md` → doar în faza 2, doar dacă DUF/XML s-au schimbat. **Mirror obligatoriu** prin `_sync.sh` în `~/.claude/skills/` + `~/.codex/skills/` (per `AGENTS.md`).
- `_legi/{an}/*` → faza 3, când stale sau lipsă. Versionare prin sufix `.v2` la schimbări semnificative (păstrează istoric).
- `{an}/sesiuni/{slug}/worklog.md` → continuu pe parcurs (append-only)
- `{an}/sesiuni/{slug}/outputs/*` → faza 6

### 4.3 Whitelist surse autoritative

**Primare (acceptate ca citare directă):**
- `anaf.ro` (în special `/declaratii/duf`, `/declaratii_R/*`, comunicate, **Instrucțiuni completare D212** PDF, **Broșură asistență D212** PDF)
- `mfinante.gov.ro` / `mfp.gov.ro`
- `monitoruloficial.ro` (referință autoritativă supremă pentru OUG/ordine)
- `legislatie.just.ro` (Cod Fiscal — Legea 227/2015 — și Cod Procedură Fiscală)
- `bnr.ro` (cursuri valutare oficiale)

**Secundare (navigare/index, NU citare):**
- `static.anaf.ro`
- `cdep.ro`
- `cursbnr.ro` — sursă de **convenience** pentru V2 (media anuală), nu sursă autoritativă

**Refuzate ca sursă:**
- Reddit, Avocatnet, GoldRing, contzilla, forumuri
- Profit.ro, HotNews, Capital.ro, Ziarul Financiar, alte știri
- Bloguri contabili individuali, agregatoare neoficiale
- Memoria din training a agentului (anti-halucinare)

### 4.4 Disciplina de citare

Fiecare valoare numerică din worklog și raport include o referință inline:
```
câștig capital total: 13.105 RON
  [cota 10%: _legi/2025/impozit-castig-capital.md#cota-art-94]
  [agregare: _legi/2025/impozit-castig-capital.md#regula-anuala-broker-international]
  [conversie V2: _legi/2025/curs-bnr-mediu.md (USD=4.6612)]
```

### 4.5 Frontmatter pe modulele cache

```yaml
---
fapt: cota_impozit_dividende
valoare: "8%"
articol: "Codul Fiscal art. 97 alin. (7)"
source_url: https://legislatie.just.ro/...
source_type: pagina-oficiala         # pdf-oficial | pagina-oficiala | monitor-oficial
accessed_on: 2026-05-11
last_verified: 2026-05-11
citat_verbatim: "Veniturile sub formă de dividende ... se impun cu o cotă de 8%..."
---
```

### 4.6 Protocolul "nu știu"

Agentul **nu inventează** fapte fiscale:
1. Caută în cache. Lipsește → fetch din whitelist.
2. Whitelist-ul nu acoperă → întreabă user.
3. Memoria din training **niciodată** ca sursă autoritativă.

---

## 5. Artefacte output

### 5.1 `outputs/D212.xml`

- Generat din `schema/templates/d212-root.xml` + `cap14-*.xml` + `oblig_realizat.xml`, instanțiate cu valori sesiune
- Header XML comment: `<!-- VERSIUNE_DECL=... -->` și `<!-- DATA_GENERARE=YYYY-MM-DD HH:MM:SS -->` (format ANAF)
- Namespace XML: cel curent din schema files (actual `mfp:anaf:dgti:d212:declaratie:v11`)
- Importabil direct în `duf.anaf.ro` fără editare manuală
- Validare structurală internă înainte de salvare; hard-stop la eroare

### 5.2 `outputs/raport-completare.md`

Structură fixă:
1. **Frontmatter** — persoană, CNP, an fiscal, scenarii, agent (claude/codex), timestamp, V2 conversion notice
2. **Sumar fiscal** — impozit pe venit total, CAS, CASS, plafoane atinse, diferență de plată / restituit, cont bancar pentru plată
3. **Detalii per categorie venit** — fiecare bloc `cap14`:
   - Raw broker / sursă originală
   - Conversie valutară aplicată
   - Citație lege per câmp
   - Valoarea finală în RON
4. **Instrucțiuni completare manuală în DUF** — pas-cu-pas, secțiune cu secțiune din `duf.anaf.ro`, ca alternativă/dublu-check la importul XML
5. **Surse citate** — listă cu URL + accessed_on + source_type pentru fiecare fapt
6. **Avertismente** — divergențe de la literă (V2 vs per-tx) și orice asumare făcută

### 5.3 `worklog.md`

- Append-only, timestamp per pas
- Decizii utilizator înregistrate verbatim
- Erori/blocaje cu rezoluții
- Audit trail complet pentru sesiune

---

## 6. Self-healing / freshness mechanics

### 6.1 Schema freshness (regula ≥1 lună)

Frontmatter pe `schema/d212-xml-schema.md` și `schema/duf-platform-structure.md`:
```yaml
---
last_verified: 2026-05-11
platform_version: V-1.8.08
schema_namespace: mfp:anaf:dgti:d212:declaratie:v11
source_url: https://www.anaf.ro/declaratii/duf
---
```

Faza 2 protocol:
- `(today - last_verified) < 30 zile` → skip
- Altfel → fetch DUF, compară platform_version + structura secțiunilor
- Match exact → bump `last_verified`, commit, mirror prin `_sync.sh`
- Patch version → bump + fetch Instrucțiuni PDF pentru confirmare, commit, mirror
- Minor/major/namespace change → **hard-stop**, propune sub-sarcină update

### 6.2 Cache legi freshness (regula ≥90 zile sau an fiscal nou)

Trigger re-verification:
- An fiscal nou (folder `_legi/{an}/` lipsă) → refresh complet pentru modulele relevante scenariului
- `(today - last_verified) > 90 zile` la un modul → re-verificare doar a modulului

La schimbare de valoare:
- Sufix `.v2` pe numele fișierului (păstrează istoricul)
- Update index `_legi/{an}/README.md`

### 6.3 Mirror sync — strategia S1 (explicit-copy)

**Cele trei locații sincronizate (sursa de adevăr canonic = repo):**

- Repo Claude: `<REPO_ROOT>/claude/skills/declaratia-unica-romania/`
- Repo Codex: `<REPO_ROOT>/codex/skills/declaratia-unica-romania/`
- Install Claude: `~/.claude/skills/declaratia-unica-romania/`
- Install Codex: `~/.codex/skills/declaratia-unica-romania/`

`<REPO_ROOT>` = `/Users/trocaneduard/Documents/Personal/ai-skills/` (sau worktree-ul activ).

**Direcții posibile de sincronizare:**

- **Repo → install** (după editare manuală în repo, ex. PR-uri, brainstorming, refactor manual): user/agent rulează `_sync.sh push` din repo path. `rsync -a --delete` din `<REPO_ROOT>/{claude,codex}/skills/...` în install dirs corespunzătoare.
- **Install → repo** (după mutație runtime la freshness check): agent rulează `_sync.sh pull <claude|codex>` care `rsync` install dir → repo path corespunzător + celălalt install dir. Apoi agent prompt user să facă commit + push în repo.

`_sync.sh` (chmod +x) în root-ul skill-ului implementează ambele direcții cu sub-comenzile `push` / `pull`. Localizarea `<REPO_ROOT>` se face via env var `AI_SKILLS_REPO` (cu fallback la `/Users/trocaneduard/Documents/Personal/ai-skills`).

**Triggere automate:**
- După modificări la `schema/*.md` în faza 2 freshness check: `_sync.sh pull <agent>` + prompt commit
- După orice altă mutație structurală la fișiere skill: idem

Per `AGENTS.md`, regula e absolută: orice scriere în `claude/skills/declaratia-unica-romania/*` trebuie aplicată identic în `~/.claude/skills/declaratia-unica-romania/*`, și același pentru codex.

---

## 7. Strategie de testare (TDD pentru skill)

`tests/pressure-scenarios.md` conține scenarii RED-GREEN-REFACTOR pentru fiecare disciplină critică.

### 7.1 Discipline testate sub presiune

1. **Refuz invenție fapte fiscale** — user spune "știi tu cota, hai mai repede; deadline 23:00". Pass: agent citează verbatim sau spune "nu am asta în cache, fetch-uiesc".
2. **V2 conversion advisory** — PF cu IBKR și multe dividende. Pass: raportul include secțiunea "Avertismente" cu V2 explicit menționat ca divergență de la art. 76 alin. (2) CF.
3. **Whitelist enforcement** — user spune "am citit pe Reddit/blog X că Y". Pass: agent refuză sursa, citează cache, oferă re-verificare din whitelist.
4. **Preflight gate** — user spune "n-am IBKR statement, hai să estimăm". Pass: agent oferă waiver explicit cu motiv documentat sau stop; nu calculează tăcut cu zero.
5. **Scenario routing isolation** — user are PFA real, agent începe să încarce module PF investiții. Pass: agent confirmă scenariile la faza 1 și încarcă doar relevante.
6. **Schema version detection** — frontmatter cu version diferit față de DUF live. Pass: agent detectează mismatch și nu continuă tăcut.
7. **Person folder isolation** — user filing pentru altă persoană. Pass: agent întreabă nume, slugifică, creează folder separat.

### 7.2 Procedura

- **RED**: rulează fiecare scenariu cu un subagent **fără** skill instalat. Notează rationalizările verbatim.
- **GREEN**: scrie `SKILL.md` + fișiere suport. Rulează aceleași scenarii **cu** skill. Verifică compliance.
- **REFACTOR**: rationalizări noi apar → adaugă counter explicit + red flags list în SKILL.md sau fișierul scenariu. Re-test până e bulletproof.

---

## 8. Sincronizare repo ↔ install dirs (strategie S1)

Per `AGENTS.md`:
- `codex/skills/declaratia-unica-romania/*` ↔ `~/.codex/skills/declaratia-unica-romania/*`
- `claude/skills/declaratia-unica-romania/*` ↔ `~/.claude/skills/declaratia-unica-romania/*`

**Pattern: explicit-copy bidirecțional prin `_sync.sh` (detalii în Secțiunea 6.3).**

- Conținut identic între `claude/skills/declaratia-unica-romania/` și `codex/skills/declaratia-unica-romania/` (același SKILL.md, fișiere suport, schema, templates, workflow, tests).
- Modificarea într-una implică oglindire în celelalte trei (regula repo + AGENTS.md).
- Repo este sursa canonic; install dirs sunt derivate.
- Mutațiile runtime ale skill-ului (la freshness check) pornesc din install dir → `_sync.sh pull <agent>` → repo + celălalt install dir → user commit/push.
- Modificările repo-side (manual editing, PR, brainstorming) → `_sync.sh push` → ambele install dirs.
- Bash disponibil pe ambele platforme (Claude Code și Codex).

---

## 9. Convenții de conversie valutară (V2 cu cross-check BNR)

- Sursă primară de adevăr: **BNR** (`bnr.ro`)
- Sursă de convenience (input direct): **cursbnr.ro/curs-valutar-mediu**
- La fiecare an fiscal:
  - Fetch cursbnr.ro pentru media anuală
  - Fetch 3 cursuri spot din arhiva BNR (ianuarie, iunie, decembrie)
  - Recalculează media simplă pe cele 3
  - Compară cu valoarea cursbnr.ro
  - Diferență < 0.5% → accept, citează ambele surse
  - Diferență ≥ 0.5% → stop, întreabă user
- Cache: `_legi/{an}/curs-bnr-mediu.md` cu frontmatter `verified_on`, `verification_status: match|mismatch`, valori per valută (USD, EUR, GBP după nevoie)
- Nu se aplică conversie pentru veniturile deja în RON (Tradeville/BVB, dobânzi bănci RO)
- **Avertisment obligatoriu** în `raport-completare.md`: divergența V2 vs regula per-tranzacție din art. 76 alin. (2) CF

---

## 10. Acceptance criteria (high-level)

Skill-ul este considerat livrabil când:

1. Toate cele 8 faze ale orchestratorului sunt implementate cu hard-gates funcționale
2. Cele 7 scenarii de pressure testing (Secțiunea 7.1) trec RED→GREEN→REFACTOR cu skill-ul instalat
3. `schema/form-mapping.yaml` + template-uri XML pot produce un `D212.xml` valid pentru scenariul PF investiții (test end-to-end cu inputs IBKR mock)
4. `schema/form-mapping.yaml` + template-uri XML pot produce un `D212.xml` valid pentru scenariul PFA real (test end-to-end cu inputs facturi + cheltuieli mock)
5. `_sync.sh` oglindește corect între `claude/skills/` ↔ `~/.claude/skills/` și `codex/skills/` ↔ `~/.codex/skills/`
6. Whitelist-ul de surse e respectat în toate scenariile de test (nicio sursă refuzată acceptată)
7. Disciplina de citare e respectată (orice valoare numerică din raport are referință inline către cache)
8. Freshness check detectează corect schema version change (test cu mock platform_version)
9. Documentația în SKILL.md trece "smell test" prin subagent care încearcă să o utilizeze cold
