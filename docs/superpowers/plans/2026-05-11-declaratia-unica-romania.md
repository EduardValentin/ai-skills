# Declarația Unică România — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `declaratia-unica-romania` skill — a Claude+Codex skill that assists annual D212 filing for PF (investments/dividends/capital gains/crypto/interest) and PFA în sistem real, sourced strictly from authoritative Romanian fiscal sources with mandatory citation discipline.

**Architecture:** Orchestrator skill (`SKILL.md` + `orchestrator.md`) with per-scenario detail files, static schema artifacts (XML schema + DUF structure + form-mapping YAML/MD + XML templates), workflow protocols (freshness, preflight, citation, currency), and a `_sync.sh` script for bidirectional mirror between `<repo>/{claude,codex}/skills/...` and `~/.{claude,codex}/skills/...`. Skill discipline is tested with TDD pressure scenarios run via subagents.

**Tech Stack:** Markdown + YAML (skill content), XML templates (D212 generation), Bash + rsync (`_sync.sh`), Python 3 stdlib (`xml.etree.ElementTree` for XML validation tests), Claude Code/Codex subagent dispatch for pressure testing.

**Source spec:** [docs/superpowers/specs/2026-05-11-declaratia-unica-romania-design.md](../specs/2026-05-11-declaratia-unica-romania-design.md)

**Reference data already in repo:**
- `/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/D212.xml` — golden XML structural reference (V-1.7.08, schema v11)
- `/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/Documente IBKR/` — real IBKR data for E2E validation
- DUF platform: `https://www.anaf.ro/declaratii/duf` (currently V-1.8.08 / 06.05.2026)

**Conventions:**
- All skill content authored in Romanian (per design decision LIM1)
- All commit messages in English, with body explaining "why"
- After EVERY commit that modifies skill files, run `_sync.sh push` to mirror to install dirs (then verify with `ls`)
- Pressure scenarios run via the `Agent` tool with `subagent_type: general-purpose`

---

## Phase 1 — Scaffold + Sync Mechanism

### Task 1.1: Create skill directory tree

**Files:**
- Create: `claude/skills/declaratia-unica-romania/` and all subdirectories
- Create: `codex/skills/declaratia-unica-romania/` and all subdirectories

- [ ] **Step 1: Create directory skeletons**

Run from repo root:
```bash
for base in claude codex; do
  mkdir -p "$base/skills/declaratia-unica-romania/schema/templates"
  mkdir -p "$base/skills/declaratia-unica-romania/workflow"
  mkdir -p "$base/skills/declaratia-unica-romania/tests"
done
```

- [ ] **Step 2: Verify structure**

Run: `find claude/skills/declaratia-unica-romania codex/skills/declaratia-unica-romania -type d | sort`

Expected output: 10 directories total (5 per base × 2 bases — root + schema + templates + workflow + tests).

- [ ] **Step 3: Add `.gitkeep` to empty leaves for tracking**

```bash
for base in claude codex; do
  for sub in schema schema/templates workflow tests; do
    touch "$base/skills/declaratia-unica-romania/$sub/.gitkeep"
  done
done
```

- [ ] **Step 4: Commit**

```bash
git add claude/skills/declaratia-unica-romania codex/skills/declaratia-unica-romania
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: scaffold skill directory tree

Mirror skeleton across claude/ and codex/ install paths so both agent
runtimes can load the skill identically.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.2: Write `_sync.sh` bidirectional sync script

**Files:**
- Create: `claude/skills/declaratia-unica-romania/_sync.sh`
- Create: `codex/skills/declaratia-unica-romania/_sync.sh` (identical copy)

- [ ] **Step 1: Write `_sync.sh`**

Path: `claude/skills/declaratia-unica-romania/_sync.sh`

```bash
#!/usr/bin/env bash
# _sync.sh — mirror skill between repo and install dirs.
#
# Usage:
#   _sync.sh push                 # repo → both install dirs (~/.claude, ~/.codex)
#   _sync.sh pull claude          # ~/.claude install dir → repo + ~/.codex install dir
#   _sync.sh pull codex           # ~/.codex install dir → repo + ~/.claude install dir
#
# Resolves repo root via $AI_SKILLS_REPO env var, fallback to a hardcoded path.

set -euo pipefail

REPO_ROOT="${AI_SKILLS_REPO:-/Users/trocaneduard/Documents/Personal/ai-skills}"
SKILL_NAME="declaratia-unica-romania"

REPO_CLAUDE="$REPO_ROOT/claude/skills/$SKILL_NAME"
REPO_CODEX="$REPO_ROOT/codex/skills/$SKILL_NAME"
INSTALL_CLAUDE="$HOME/.claude/skills/$SKILL_NAME"
INSTALL_CODEX="$HOME/.codex/skills/$SKILL_NAME"

usage() {
  cat >&2 <<USAGE
Usage:
  $0 push                 # repo → both install dirs
  $0 pull claude|codex    # named install dir → repo + other install dir
USAGE
  exit 1
}

rsync_clone() {
  local src="$1"; local dst="$2"
  mkdir -p "$dst"
  rsync -a --delete --exclude=".gitkeep" "$src/" "$dst/"
  echo "synced: $src → $dst"
}

cmd="${1:-}"
case "$cmd" in
  push)
    [ -d "$REPO_CLAUDE" ] || { echo "missing: $REPO_CLAUDE" >&2; exit 2; }
    [ -d "$REPO_CODEX" ]  || { echo "missing: $REPO_CODEX"  >&2; exit 2; }
    rsync_clone "$REPO_CLAUDE" "$INSTALL_CLAUDE"
    rsync_clone "$REPO_CODEX"  "$INSTALL_CODEX"
    ;;
  pull)
    agent="${2:-}"
    case "$agent" in
      claude)
        [ -d "$INSTALL_CLAUDE" ] || { echo "missing: $INSTALL_CLAUDE" >&2; exit 2; }
        rsync_clone "$INSTALL_CLAUDE" "$REPO_CLAUDE"
        rsync_clone "$INSTALL_CLAUDE" "$REPO_CODEX"
        rsync_clone "$INSTALL_CLAUDE" "$INSTALL_CODEX"
        echo "remember: commit and push the repo changes"
        ;;
      codex)
        [ -d "$INSTALL_CODEX" ] || { echo "missing: $INSTALL_CODEX" >&2; exit 2; }
        rsync_clone "$INSTALL_CODEX" "$REPO_CODEX"
        rsync_clone "$INSTALL_CODEX" "$REPO_CLAUDE"
        rsync_clone "$INSTALL_CODEX" "$INSTALL_CLAUDE"
        echo "remember: commit and push the repo changes"
        ;;
      *) usage ;;
    esac
    ;;
  *) usage ;;
esac
```

- [ ] **Step 2: Make executable and copy to codex base**

```bash
chmod +x claude/skills/declaratia-unica-romania/_sync.sh
cp claude/skills/declaratia-unica-romania/_sync.sh codex/skills/declaratia-unica-romania/_sync.sh
chmod +x codex/skills/declaratia-unica-romania/_sync.sh
```

- [ ] **Step 3: Smoke test `_sync.sh push`**

Run:
```bash
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh push
```

Expected: 2 "synced:" lines, no errors. Then verify install dirs exist:
```bash
ls ~/.claude/skills/declaratia-unica-romania/ ~/.codex/skills/declaratia-unica-romania/
```

Expected: both list `_sync.sh schema workflow tests` (or similar; `.gitkeep` excluded by rsync filter).

- [ ] **Step 4: Smoke test `_sync.sh pull claude`**

Add a marker file to the claude install dir:
```bash
echo "marker" > ~/.claude/skills/declaratia-unica-romania/_marker.txt
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh pull claude
```

Expected: 3 "synced:" lines + "remember:" message. Verify:
```bash
test -f claude/skills/declaratia-unica-romania/_marker.txt && echo "OK repo got marker"
test -f codex/skills/declaratia-unica-romania/_marker.txt && echo "OK codex repo got marker"
test -f ~/.codex/skills/declaratia-unica-romania/_marker.txt && echo "OK codex install got marker"
```

Expected: 3 "OK" lines. Clean up:
```bash
rm claude/skills/declaratia-unica-romania/_marker.txt
rm codex/skills/declaratia-unica-romania/_marker.txt
rm ~/.claude/skills/declaratia-unica-romania/_marker.txt
rm ~/.codex/skills/declaratia-unica-romania/_marker.txt
```

- [ ] **Step 5: Commit**

```bash
git add claude/skills/declaratia-unica-romania/_sync.sh codex/skills/declaratia-unica-romania/_sync.sh
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add bidirectional sync script

_sync.sh implements push (repo → install dirs) and pull (install dir →
repo + other install dir) using rsync -a --delete. AI_SKILLS_REPO env
var locates the repo, with a hardcoded fallback. The pull mode emits a
reminder to commit the repo changes after a runtime mutation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Schema Artifacts

### Task 2.1: `schema/d212-xml-schema.md` — XML schema reference

**Files:**
- Create: `claude/skills/declaratia-unica-romania/schema/d212-xml-schema.md`

- [ ] **Step 1: Inspect the golden XML reference**

Read `/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/D212.xml` (in repo as context — already loaded once during brainstorming). Confirm the namespace, version comment, root element attributes, `<oblig_realizat>` attribute set, and `<cap14>` attribute set match the spec.

- [ ] **Step 2: Write `schema/d212-xml-schema.md`**

```markdown
---
last_verified: 2026-05-11
platform_version: V-1.8.08
schema_namespace: mfp:anaf:dgti:d212:declaratie:v11
source_url: https://www.anaf.ro/declaratii/duf
source_anchor_xml: /Users/trocaneduard/Documents/Personal/declaratii-unice/2025/D212.xml
---

# Schema XML D212

Documentul descrie structura XML produsă/importată de platforma DUF (`duf.anaf.ro`). Toate atributele și elementele sunt extrase din `D212.xml` golden reference (vezi `source_anchor_xml`). Înainte de orice generare XML în faza 6 a sesiunii, verifică `last_verified` și `platform_version` față de pagina DUF live (vezi `../workflow/freshness-check.md`).

## Header

Două comentarii XML obligatorii la începutul fișierului:

```xml
<?xml version="1.0"?>
<!-- VERSIUNE_DECL=V-1.7.08 / 12.03.2026 -->
<!-- DATA_GENERARE=2026-03-19 18:20:20 -->
```

- `VERSIUNE_DECL` = `platform_version` curent emis de DUF (frontmatter aici).
- `DATA_GENERARE` = timestamp ISO la momentul generării de către skill.

## Element root `<d212>`

Namespace: `mfp:anaf:dgti:d212:declaratie:v11`.

Atribute (toate obligatorii):

| Atribut | Tip | Sursă |
|---|---|---|
| `an_r` | string anul (`"2026"` = anul calendaristic al depunerii) | sesiune (`{an_fiscal} + 1`) |
| `luna_r` | `"12"` (luna de referință închidere an fiscal) | constant |
| `d_rec`, `rectif1`, `rectif2` | flag-uri rectificare; `"0"` la declarație inițială | sesiune |
| `totalPlata_A` | total de plată în lei | calculat |
| `bifa_conformare`, `bifa18`, `bifa19`, `bifa23` | bife procedură; default `"0"` | sesiune |
| `anulare_litA`, `anulare_litB` | flag anulare; `"0"` la declarație inițială | sesiune |
| `bifa111`, `bifa112`, `bifa113`, `bifa121`, `bifa122`, `bifa131`, `bifa132`, `bifa14`, `bifa15` | bife subcapitole; `"1"` activează secțiunea corespunzătoare | sesiune (per scenariu) |
| `nume_c`, `initiala_c`, `prenume_c` | identitate fiscală | persoană sesiune |
| `cif` | CNP / CIF persoană | persoană sesiune |
| `cont_bancar` | IBAN pentru restituiri | persoană sesiune |
| `telefon_c`, `email_c` | contact | persoană sesiune |
| `nerezident` | `"0"` rezident, `"1"` nerezident | persoană sesiune |
| `xmlns`, `xmlns:xsi`, `xsi:schemaLocation` | namespaces (constante) | constant |

**Mapare bife → subcapitole** (de actualizat prin re-verificare DUF dacă schimbă):
- `bifa121="1"` — Cap. I.1 (venituri realizate din România)
- `bifa122="1"` — Cap. I.2 (venituri realizate din străinătate)
- `bifa131="1"` — Cap. I.3 (CAS estimat anul curent)
- `bifa132="1"` — Cap. I.4 / Date CASS pentru venituri investiții
- (alte bife: verifică Instrucțiunile PDF anuale)

## Element `<oblig_realizat>`

Conține obligațiile calculate pe baza veniturilor realizate. Atribute relevante (toate `integer_lei` dacă nu se specifică altfel):

| Atribut | Semnificație | Calcul |
|---|---|---|
| `cass_ven_dpi` | CASS din drepturi proprietate intelectuală | calculat |
| `cass_ven_asc` | CASS asociere | calculat |
| `cass_ven_cfb` | CASS contracte fără bază | calculat |
| `cass_ven_inv` | CASS din venituri investiții | calculat |
| `cass_ven_asp` | CASS asistență persoană | calculat |
| `cass_ven_alt` | CASS alte venituri | calculat |
| `cass_total_ven` | total venituri pentru bază CASS | sumă |
| `cass_baza` | baza CASS (min cu 12×salariu_min sau efectiv, după caz) | calculat per `_legi/{an}/plafoane-cass.md` |
| `cass_anuala` | 10% × `cass_baza` | calculat |
| `cass_datorat_art180`, `cass_datorat` | datorat după ajustări | calculat |
| `cass_retinut` | reținut la sursă (broker RO, etc.) | input |
| `cass_dif_plus`, `cass_dif_minus` | diferențe față de reținut | calculat |
| `bifa_cass_real` | indicator regim CASS (3 = venituri investiții?) | sesiune |
| `bifa_cass_datorat_dpi`, `bifa_cass_datorat_ai` | tip CASS datorat | sesiune |
| `oblimpoz_real_total`, `oblimpoz_real_dif_deplata`, `oblimpoz_real_dif_restituit` | impozit total / diferențe | calculat |
| `oblcas_real_difPlus`, `oblcas_real_str` | diferențe CAS | calculat |
| `oblcass_real_difMinus_174`, `oblcass_real_difPlus_dpi`, `oblcass_real_difMinus_dpi`, `oblcass_real_str`, `oblcass_real_str_pensie` | diferențe CASS pe sub-rubrici | calculat |
| `impozit_venit_plus`, `impozit_venit_minus` | impozit net plată/restituire | calculat |
| `cas_plus`, `cass_plus`, `cass_minus` | totaluri | calculat |
| `dif_de_plata`, `dif_de_restituit` | totalul final | calculat |

## Element `<cap14>` (per linie de venit străinătate/România)

Atribute (selectate per categorie de venit; vezi `form-mapping.yaml` pentru regula exactă required/optional):

| Atribut | Tip | Sursă |
|---|---|---|
| `str_stat_realiz_v` | ISO-3166-alpha2 (ex. `"US"`, `"CY"`); absent la venituri RO | input |
| `den_stat` | denumirea statului în română (ex. `"Statele Unite ale Americii"`) | derivat din ISO |
| `str_categ_venit` | cod categorie (`"2012"`, `"2017"`, `"2018"`, etc.) | form-mapping |
| `den_categ_venit` | denumire completă | derivat din cod |
| `dubla_impunere` | `"1"` dacă există tratat și impozit plătit străinătate | derivat |
| `str_venit_net_anual` | venit net anual (integer_lei) | calculat |
| `str_pierdere_precedenta` | pierdere reportată din anul precedent | input (D212 anterior) |
| `str_pierdere_compensata` | pierdere efectiv compensată în anul curent | calculat |
| `str_venit_recalculat` | venit după compensare pierdere | calculat |
| `str_impozit_datorat_Ro` | impozit calculat în RO | calculat |
| `str_impozit_platit` | impozit plătit străinătate | input (broker) |
| `str_credit_fiscal` | credit fiscal (min între impozit plătit și impozit RO, plafonat) | calculat |
| `str_dif_impozit_datorat` | impozit RO final (datorat RO - credit fiscal) | calculat |

## Codurile de categorie venit (verifică anual din Instrucțiuni)

| Cod | Denumire | Context | Sub-element XML |
|---|---|---|---|
| `2012` | Transferul titlurilor de valoare și orice alte operațiuni cu instrumente financiare, inclusiv instrumente financiare derivate, precum și transferul aurului financiar | câștig capital broker, cripto | `cap14` |
| `2017` | Dobânzi | conturi de economii, depozite, obligațiuni străinătate | `cap14` |
| `2018` | Dividende | dividende străinătate sau RO ne-reținute la sursă | `cap14` |

**Reverificare obligatorie:** la fiecare freshness check (Faza 2), re-fetch din Instrucțiuni PDF ANAF pentru anul fiscal curent. Lista poate crește (DPI, chirii etc.) — dar acest skill acoperă strict `2012`/`2017`/`2018` și PFA real (separat, codat în `pfa-real.md`).
```

- [ ] **Step 3: Commit**

```bash
git add claude/skills/declaratia-unica-romania/schema/d212-xml-schema.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: document D212 XML schema

Captures the v11 namespace, root <d212> attributes, <oblig_realizat>
CASS/impozit fields, and <cap14> per-line attributes from the 2025
golden XML reference. Includes the 2012/2017/2018 category codes with
explicit reverification trigger at every freshness check.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.2: `schema/duf-platform-structure.md` — DUF platform reference

**Files:**
- Create: `claude/skills/declaratia-unica-romania/schema/duf-platform-structure.md`

- [ ] **Step 1: Write the file**

```markdown
---
last_verified: 2026-05-11
platform_version: V-1.8.08
source_url: https://www.anaf.ro/declaratii/duf
---

# Structura platformei DUF (duf.anaf.ro)

Platforma web ANAF pentru completarea D212. Sursa pentru maparea "ce label apare în UI" ↔ "ce atribut XML rezultă".

## Secțiuni principale

1. **Date de identificare** — CNP, nume, adresă, IBAN, contact. Mapează pe atributele root `<d212>` (`nume_c`, `prenume_c`, `cif`, `cont_bancar`, `telefon_c`, `email_c`, `nerezident`).
2. **Venituri realizate** — capitolul I al declarației. Conține butoanele de adăugare:
   - **"Adaugă venit străinătate"** → generează un element `<cap14>` cu `str_stat_realiz_v` populat
   - **"Adaugă venit România"** → generează un element `<cap14>` fără `str_stat_realiz_v`
   - În interiorul fiecărei adăugări, dropdown pentru categorie venit (`2012`, `2017`, `2018`, ...)
3. **Venituri cu reținere la sursă** — venituri unde plătitorul (broker RO, bancă RO, etc.) a reținut deja impozitul. Folosit doar informativ pentru reconciliere CASS; nu generează `cap14`.
4. **Date privind CAS** — pentru PFA, contribuție de asigurări sociale. Mapează pe sub-set din `<oblig_realizat>`.
5. **Date privind CASS** — contribuție asigurări sănătate. Bifa de regim (`bifa_cass_real`), tip venit (DPI / venituri investiții / etc.), bază (`cass_baza`), CASS anuală.

## Opțiuni adiacente

- **Bonificație impozit** — reducere impozit dacă se plătește în avans (verifică termenul anual)
- **CASS prin opțiune** — declarare CASS opțional când veniturile sunt sub plafon
- **Persoane în întreținere** — deduceri

## Output

- **Descarcă XML** — fișier `D212.xml` cu schema namespace `mfp:anaf:dgti:d212:declaratie:v11`. Importabil înapoi în DUF.
- **Descarcă PDF** — varianta tipăribilă (nu se folosește pentru submit electronic).

## Resurse oficiale linkate de DUF

Toate sunt sursă **primară autoritativă** (whitelist confirmat):

- **Instrucțiuni de completare a declarației unice** — PDF ANAF per an fiscal
- **Broșură de asistență** — PDF ANAF
- **Norme de venit 2025** — PDF ANAF (irelevant pentru acest skill, dar listat)

## Autentificare

Mediu: **Public** (fără autentificare pentru completare și export XML). Autentificarea SPV (cu certificat digital sau credențiale ANAF) este necesară doar pentru **submit electronic** — în afara scope-ului acestui skill.

## Reverificare

La fiecare freshness check (≥ 30 zile), fetch `https://www.anaf.ro/declaratii/duf` și verifică:
- Footer-ul pentru `platform_version` (frontmatter aici)
- Lista celor 5 secțiuni principale e neschimbată
- Butoanele "Adaugă venit străinătate/România" sunt încă prezente

Dacă oricare s-a schimbat → hard-stop, prompt user (vezi `../workflow/freshness-check.md`).
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/declaratia-unica-romania/schema/duf-platform-structure.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: document DUF platform structure

Captures the 5-section layout of duf.anaf.ro (identification, income
realized, withholding-at-source, CAS, CASS), the "Adaugă venit
străinătate/România" mapping to <cap14>, output format, and authoritative
resource links shown by the platform itself.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.3: `schema/form-mapping.yaml` — structured mapping

**Files:**
- Create: `claude/skills/declaratia-unica-romania/schema/form-mapping.yaml`

- [ ] **Step 1: Write the YAML**

```yaml
# form-mapping.yaml
# Structured mapping: categorie venit ↔ atribute XML ↔ secțiune DUF.
# Companion narrative: form-mapping.md
# Sync rules: schema-validator.md
# Last sync with d212-xml-schema.md: 2026-05-11

meta:
  schema_namespace: mfp:anaf:dgti:d212:declaratie:v11
  last_synced_with_xml_schema: 2026-05-11

categorii_venit:
  - cod: "2012"
    denumire: "Transferul titlurilor de valoare și orice alte operațiuni cu instrumente financiare, inclusiv instrumente financiare derivate, precum și transferul aurului financiar"
    sursa_posibila: [strainatate, romania]
    capitol_xml: cap14
    duf_section: "Venituri realizate → Adaugă venit {sursa} → Categorie 2012"
    campuri:
      str_stat_realiz_v:
        required_if: "sursa == strainatate"
        type: ISO-3166-alpha2
        sursa_date: "input.country_of_broker"
      str_categ_venit:
        required: true
        type: string
        constant: "2012"
      den_categ_venit:
        required: true
        type: string
        constant: "Transferul titlurilor de valoare și orice alte operațiuni cu instrumente financiare, inclusiv instrumente financiare derivate, precum și transferul aurului financiar"
      str_venit_net_anual:
        required: true
        type: integer_lei
        sursa_date: "calc.net_gain_RON"
        calcul_ref: "../pf-investitii.md#calcul-cap-2012"
      str_pierdere_precedenta:
        required: false
        type: integer_lei
        sursa_date: "input.d212_anul_precedent.pierdere_reportata_2012"
      str_pierdere_compensata:
        required: true
        type: integer_lei
        calcul_ref: "../pf-investitii.md#compensare-pierderi"
      str_venit_recalculat:
        required: true
        type: integer_lei
        formula: "str_venit_net_anual - str_pierdere_compensata"
      str_impozit_datorat_Ro:
        required: true
        type: integer_lei
        formula: "round(str_venit_recalculat * cota_2012)"
        cache_ref: "_legi/{an}/impozit-castig-capital.md#cota-art-94"
      str_impozit_platit:
        required_if: "sursa == strainatate AND broker_aplica_retinere"
        type: integer_lei
        sursa_date: "input.foreign_tax_withheld_RON"
      str_credit_fiscal:
        required_if: "dubla_impunere == 1"
        type: integer_lei
        formula: "min(str_impozit_platit, str_impozit_datorat_Ro)"
        cache_ref: "_legi/{an}/tratate-dubla-impunere.md"
      str_dif_impozit_datorat:
        required: true
        type: integer_lei
        formula: "str_impozit_datorat_Ro - str_credit_fiscal"
    citation_required:
      - "_legi/{an}/impozit-castig-capital.md#cota-art-94"
      - "_legi/{an}/impozit-castig-capital.md#regula-anuala-broker-international"
      - "_legi/{an}/tratate-dubla-impunere.md"   # numai dacă străinătate

  - cod: "2017"
    denumire: "Dobânzi"
    sursa_posibila: [strainatate, romania]
    capitol_xml: cap14
    duf_section: "Venituri realizate → Adaugă venit {sursa} → Categorie 2017"
    campuri:
      str_stat_realiz_v:
        required_if: "sursa == strainatate"
        type: ISO-3166-alpha2
        sursa_date: "input.country_of_payer"
      str_categ_venit:
        constant: "2017"
      den_categ_venit:
        constant: "Dobânzi"
      str_venit_net_anual:
        required: true
        type: integer_lei
        sursa_date: "calc.interest_RON"
        calcul_ref: "../pf-investitii.md#calcul-cap-2017"
      str_pierdere_compensata:
        required: true
        type: integer_lei
        default: 0
      str_venit_recalculat:
        formula: "str_venit_net_anual - str_pierdere_compensata"
      str_impozit_datorat_Ro:
        formula: "round(str_venit_recalculat * cota_2017)"
        cache_ref: "_legi/{an}/impozit-dobanzi.md#cota"
      str_impozit_platit:
        required_if: "sursa == strainatate AND broker_aplica_retinere"
        type: integer_lei
      str_credit_fiscal:
        required_if: "dubla_impunere == 1"
        formula: "min(str_impozit_platit, str_impozit_datorat_Ro)"
      str_dif_impozit_datorat:
        formula: "str_impozit_datorat_Ro - str_credit_fiscal"
    citation_required:
      - "_legi/{an}/impozit-dobanzi.md#cota"
      - "_legi/{an}/tratate-dubla-impunere.md"

  - cod: "2018"
    denumire: "Dividende"
    sursa_posibila: [strainatate, romania]
    capitol_xml: cap14
    duf_section: "Venituri realizate → Adaugă venit {sursa} → Categorie 2018"
    campuri:
      str_stat_realiz_v:
        required_if: "sursa == strainatate"
      str_categ_venit:
        constant: "2018"
      den_categ_venit:
        constant: "Dividende"
      dubla_impunere:
        type: boolean_01
        rule: "true (1) dacă țara are tratat de evitare a dublei impuneri cu România ȘI s-a reținut impozit străinătate"
        cache_ref: "_legi/{an}/tratate-dubla-impunere.md"
      str_venit_net_anual:
        required: true
        type: integer_lei
        sursa_date: "calc.dividend_gross_RON"
        calcul_ref: "../pf-investitii.md#calcul-cap-2018"
      str_pierdere_compensata:
        type: integer_lei
        default: 0
      str_venit_recalculat:
        formula: "str_venit_net_anual - str_pierdere_compensata"
      str_impozit_datorat_Ro:
        formula: "round(str_venit_recalculat * cota_2018)"
        cache_ref: "_legi/{an}/impozit-dividende.md#cota"
      str_impozit_platit:
        required_if: "dubla_impunere == 1"
        sursa_date: "input.foreign_tax_withheld_RON"
      str_credit_fiscal:
        required_if: "dubla_impunere == 1"
        formula: "min(str_impozit_platit, str_impozit_datorat_Ro)"
      str_dif_impozit_datorat:
        formula: "str_impozit_datorat_Ro - str_credit_fiscal"
    citation_required:
      - "_legi/{an}/impozit-dividende.md#cota"
      - "_legi/{an}/tratate-dubla-impunere.md"

# Note: PFA în sistem real nu folosește <cap14> ci alte capitole (a se determina
# din Instrucțiuni la freshness check). Mapping-ul PFA real va fi adăugat la
# Task 2.3.B într-o iterație ulterioară dacă scenariul PFA e activat în sesiune.
# Pentru moment, scope-ul YAML acoperă strict capitolele <cap14> cu codurile
# 2012/2017/2018 și obligațiile <oblig_realizat>.

oblig_realizat:
  duf_section: "Date privind CASS / Date privind CAS / sumar fiscal"
  campuri:
    cass_ven_inv:
      sursa_date: "calc.cass_baza_din_venituri_investitii"
      calcul_ref: "../pf-investitii.md#cass-baza"
    cass_baza:
      type: integer_lei
      formula: "min(cass_total_ven, 12 * salariu_minim_brut)"
      cache_ref: "_legi/{an}/plafoane-cass.md"
      note: "plafon 12 salarii minime brute conform art. 174 CF"
    cass_anuala:
      type: integer_lei
      formula: "round(cass_baza * 0.10)"
      cache_ref: "_legi/{an}/plafoane-cass.md#cota"
    cass_retinut:
      type: integer_lei
      sursa_date: "input.cass_retinut_broker_RO_sau_banca"
    cass_dif_plus:
      formula: "max(0, cass_anuala - cass_retinut)"
    cass_dif_minus:
      formula: "max(0, cass_retinut - cass_anuala)"
    dif_de_plata:
      formula: "impozit_venit_plus + cas_plus + cass_plus"
    dif_de_restituit:
      formula: "impozit_venit_minus + cass_minus"
```

- [ ] **Step 2: Validate YAML syntactically**

Run: `python3 -c "import yaml; yaml.safe_load(open('claude/skills/declaratia-unica-romania/schema/form-mapping.yaml'))"`

Expected: no output, exit code 0. If yaml not installed: `pip install pyyaml` then retry.

- [ ] **Step 3: Commit**

```bash
git add claude/skills/declaratia-unica-romania/schema/form-mapping.yaml
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add form-mapping YAML

Structured mapping for categories 2012/2017/2018 and <oblig_realizat>:
each XML field has type, required-if rule, formula or source-data slot,
calcul_ref pointing into scenario files, and citation_required list of
legi cache anchors. PFA real mapping is deferred; YAML currently covers
the PF investiții scope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.4: `schema/form-mapping.md` — narrative companion

**Files:**
- Create: `claude/skills/declaratia-unica-romania/schema/form-mapping.md`

- [ ] **Step 1: Write the companion**

```markdown
---
companion_of: form-mapping.yaml
last_synced: 2026-05-11
---

# Form mapping — companion narativ

Acest document explică **cum umpli fiecare câmp** din `form-mapping.yaml`. YAML-ul e sursa structurată (mașină); md-ul e sursa pentru raționament uman (cum culegi datele, ce întrebări pui utilizatorului, ce capcane evit).

Regulă strictă (vezi `schema-validator.md`): orice schimbare în YAML trebuie reflectată aici și viceversa. Câmpurile YAML fără descriere aici sau secțiunile aici fără ancore în YAML sunt erori.

## Categoria 2012 — Transferul titlurilor de valoare

**Context:** câștiguri/pierderi din vânzarea acțiunilor, ETF-uri, instrumente financiare derivate, cripto. Sursa primară: rapoarte broker (IBKR `annual_activity_statement_*.pdf` + `*.csv`, Tradeville/BVB raport anual).

**Cum se completează:**

- `str_stat_realiz_v` — codul ISO-3166-alpha2 al țării unde e listat brokerul (IBKR → `"US"` indiferent unde tranzacționează tu; Tradeville → câmp absent, e venit RO).
- `str_venit_net_anual` — câștigul net **anual agregat** în RON, calculat din raportul broker. **NU per tranzacție**: regula ANAF pentru brokeri internaționali fără reținere la sursă e agregare anuală cu metoda FIFO. Vezi `../pf-investitii.md#calcul-cap-2012` pentru pas cu pas.
- `str_pierdere_precedenta` — dacă în anul fiscal precedent ai avut pierdere reportată pentru cod 2012, citeste-o din D212-ul anului trecut, atributul `str_pierdere_compensata` (sau pierdere ne-compensată).
- `str_pierdere_compensata` — pierderea efectiv compensată în anul curent (= min cu `str_venit_net_anual`).
- `str_venit_recalculat` — automatic = `str_venit_net_anual - str_pierdere_compensata`.
- `str_impozit_datorat_Ro` — `round(str_venit_recalculat * cota)`. Cota e în `_legi/{an}/impozit-castig-capital.md#cota-art-94`.
- `str_impozit_platit` — în general 0 pentru câștig capital la broker internațional (US nu reține pe câștig capital, doar pe dividende). Verifică totuși cu raportul.
- `str_credit_fiscal` — `min(impozit_platit, impozit_datorat_Ro)`. Pentru câștig capital la broker US: 0.
- `str_dif_impozit_datorat` — `impozit_datorat_Ro - credit_fiscal`.

**Capcane:**
- IBKR raportează în USD. Folosește cursbnr.ro media anuală pentru conversie (vezi `../workflow/currency-conversion.md`).
- Cripto: dacă brokerul nu raportează FIFO, agentul trebuie să-l calculeze din lista tranzacții. Cere user-ului confirmare metodă.
- Instrumente derivate (opțiuni, futures): la fel — cod 2012, dar raportul broker poate folosi alt format (mark-to-market). Cere user-ului clarificare dacă raportul nu e linear.

## Categoria 2017 — Dobânzi

**Context:** dobânzi la conturi de economii, depozite la termen, obligațiuni străinătate. Sursa: extras bancar / situație fiscală bancă (RO), raport broker pentru obligațiuni străinătate.

**Cum se completează:**

- `str_stat_realiz_v` — codul țării băncii / emitentului. Pentru bancă RO, absent.
- `str_venit_net_anual` — total dobânzi încasate brut în RON. Pentru dobânzi RO de la bănci comerciale, băncile rețin deja impozit la sursă — verifică dacă trebuie totuși declarate (vezi `_legi/{an}/impozit-dobanzi.md`).
- `str_impozit_platit` — pentru dobânzi din străinătate cu tratat de dublă impunere și reținere la sursă, suma reținută în RON.
- `str_credit_fiscal` — la fel ca 2012.

**Capcane:**
- Dobânzile reținute la sursă în RO **nu se declară din nou** (sunt taxate definitiv) — verifică legea anuală.
- Obligațiuni de stat RO sunt scutite — verifică `_legi/{an}/impozit-dobanzi.md`.

## Categoria 2018 — Dividende

**Context:** dividende din acțiuni proprii (broker RO sau internațional). Sursa: IBKR `*.dividends.html`, `*.f1042S.pdf` (raport reținere impozit străinătate), hotărâre AGA + notă plată impozit (broker/companie RO).

**Cum se completează:**

- `str_stat_realiz_v` — codul țării companiei plătitoare. Dividend Apple → US; dividend BVB → câmp absent.
- `dubla_impunere` — `"1"` dacă: (a) țara are tratat cu România (în `_legi/{an}/tratate-dubla-impunere.md`) ȘI (b) s-a reținut impozit la sursă în acea țară. Altfel `"0"`.
- `str_venit_net_anual` — total dividende **brute** (înainte de reținere străinătate) în RON. Pentru IBKR, suma "Gross Amount" din `dividends.html`.
- `str_impozit_platit` — total impozit reținut în străinătate (pentru IBKR US standard 15% cu W-8BEN), în RON.
- `str_credit_fiscal` — `min(impozit_platit, impozit_datorat_Ro)`.
- `str_dif_impozit_datorat` — `impozit_datorat_Ro - credit_fiscal`.

**Capcane:**
- Dividendele RO de la companii listate (BVB) sunt cu reținere la sursă — declarate la cod 2018 doar dacă **NU** au fost reținute la sursă (rar, ex. distribuiri din SRL fără reținere).
- W-8BEN/W-8BEN-E semnat la broker = reținere 15% (default este 30%). Verifică formularul.
- Dividende cripto (staking, etc.) — clasificare ambiguă; cere user-ului context și consultă `_legi/{an}/impozit-cripto.md`.

## <oblig_realizat> — calcul CASS și sumar fiscal

**CASS pentru venituri investiții** (cod `cass_ven_inv`):
- Bază: suma veniturilor nete din investiții (cod 2012, 2017, 2018, 2018-RO etc.)
- Plafon: 12 × salariu_minim_brut (vezi `_legi/{an}/plafoane-cass.md`). Pentru 2025: 8.100 × 12 = 97.200 RON.
- Dacă bază < plafon mic (6 × salariu_min): nu se datorează CASS — verifică pragul anual.
- `cass_anuala = round(cass_baza * 0.10)` = 10%.
- `cass_retinut` = CASS deja reținut la sursă (broker RO uneori, bănci pentru dobânzi). De obicei 0 pentru broker internațional.
- `cass_dif_plus / cass_dif_minus` = diferența.

**Sumar fiscal:**
- `dif_de_plata` = total ce trebuie plătit la ANAF (impozit + CAS + CASS)
- `dif_de_restituit` = total ce ANAF îți întoarce
- Plata se face la cont ANAF din `cont_bancar` declarant — vezi instrucțiuni anuale pentru cont destinație ANAF.
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/declaratia-unica-romania/schema/form-mapping.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add form-mapping narrative companion

Explains how to populate each XML field per category (2012/2017/2018)
and <oblig_realizat>: data sources, calculation references, edge cases
(IBKR W-8BEN, FIFO crypto, RO withholding), and capcane. Yaml + md must
stay in sync per schema-validator.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.5: `schema/schema-validator.md` — sync rules

**Files:**
- Create: `claude/skills/declaratia-unica-romania/schema/schema-validator.md`

- [ ] **Step 1: Write the validator doc**

```markdown
# Schema validator — sync rules

Cele trei fișiere din `schema/` trebuie să rămână sincronizate:

- `d212-xml-schema.md` — sursa de adevăr pentru atribute XML, elemente, namespace
- `form-mapping.yaml` — sursa structurată pentru mapare categorie ↔ atribute
- `form-mapping.md` — narativul companion pentru YAML
- `templates/*.xml` — template-uri parametrizabile

## Reguli stricte

1. **Orice atribut XML adăugat în `d212-xml-schema.md` trebuie să apară în template-ul XML relevant** (`templates/d212-root.xml` pentru root, `templates/cap14-*.xml` pentru cap14, `templates/oblig_realizat.xml` pentru obligații).

2. **Orice câmp în `form-mapping.yaml` trebuie să aibă descriere în `form-mapping.md`.** Reciproc: orice secțiune în md trebuie să corespundă unei intrări YAML.

3. **Schimbarea `schema_namespace` în orice fișier** trebuie propagată în:
   - `d212-xml-schema.md` frontmatter
   - `form-mapping.yaml` `meta.schema_namespace`
   - `templates/d212-root.xml` element `xmlns` și `xsi:schemaLocation`

4. **Adăugarea unui nou cod de categorie venit** (ex. 2019) cere:
   - Update în `d212-xml-schema.md` secțiunea "Codurile de categorie venit"
   - Adăugare în `form-mapping.yaml` sub `categorii_venit`
   - Adăugare secțiune dedicată în `form-mapping.md`
   - Update în `pf-investitii.md` sau `pfa-real.md` dacă scenariul îl folosește

5. **Toate fișierele schema au frontmatter `last_verified`** care se actualizează atomic la freshness check. Dacă unul are dată mai veche decât altele, e desincronizare — declanșează re-verificare manuală.

## Procedura de re-sincronizare

Când freshness check (Faza 2) detectează schimbare la DUF:

1. Update `d212-xml-schema.md` și `duf-platform-structure.md` cu noile valori
2. Compară lista atributelor și codurilor cu `form-mapping.yaml`
3. Adăugă/modifică intrările YAML
4. Update `form-mapping.md` cu secțiuni / capcane noi
5. Regenerează template-urile XML dacă structura s-a schimbat
6. Run `_sync.sh pull <agent>` pentru a propaga în repo + celălalt install dir
7. Commit + push

## Test manual de sincronizare (opțional, pentru audit)

Scan rapid:

```bash
# 1. Toate codurile din YAML apar în d212-xml-schema.md tabel?
python3 -c "
import yaml, re
m = yaml.safe_load(open('claude/skills/declaratia-unica-romania/schema/form-mapping.yaml'))
yaml_codes = {c['cod'] for c in m['categorii_venit']}
schema_md = open('claude/skills/declaratia-unica-romania/schema/d212-xml-schema.md').read()
schema_codes = set(re.findall(r'\`(\d{4})\`', schema_md))
missing = yaml_codes - schema_codes
extra = schema_codes - yaml_codes
if missing: print('YAML codes missing in schema md:', missing)
if extra: print('schema md codes missing in YAML:', extra)
if not missing and not extra: print('codes in sync')
"
```

Expected: `codes in sync` line.
```

- [ ] **Step 2: Run the sync test**

Run the Python snippet from Step 1, section "Test manual de sincronizare".

Expected output: `codes in sync` (since YAML has 2012/2017/2018 and schema md has the same three).

- [ ] **Step 3: Commit**

```bash
git add claude/skills/declaratia-unica-romania/schema/schema-validator.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add schema sync rules

Documents the invariants between d212-xml-schema.md, form-mapping.yaml,
form-mapping.md, and templates/*.xml — namespace propagation, category
code parity, template/attribute coverage, frontmatter freshness atomicity.
Includes a quick Python sync check.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.6: XML templates

**Files:**
- Create: `claude/skills/declaratia-unica-romania/schema/templates/d212-root.xml`
- Create: `claude/skills/declaratia-unica-romania/schema/templates/oblig_realizat.xml`
- Create: `claude/skills/declaratia-unica-romania/schema/templates/cap14-strainatate.xml`
- Create: `claude/skills/declaratia-unica-romania/schema/templates/cap14-romania.xml`

- [ ] **Step 1: Write `d212-root.xml`**

```xml
<?xml version="1.0"?>
<!-- VERSIUNE_DECL={{platform_version}} -->
<!-- DATA_GENERARE={{data_generare_iso}} -->
<d212
  an_r="{{an_r}}"
  luna_r="12"
  d_rec="0"
  rectif1="0"
  rectif2="0"
  totalPlata_A="{{totalPlata_A}}"
  bifa_conformare="0"
  bifa18="0"
  bifa19="0"
  bifa23="0"
  anulare_litA="0"
  anulare_litB="0"
  bifa111="0"
  bifa112="0"
  bifa14="0"
  bifa113="0"
  bifa121="{{bifa121}}"
  bifa15="0"
  bifa122="{{bifa122}}"
  bifa131="0"
  bifa132="{{bifa132}}"
  nume_c="{{nume}}"
  initiala_c="{{initiala_tata}}"
  prenume_c="{{prenume}}"
  cif="{{cnp}}"
  cont_bancar="{{iban}}"
  telefon_c="{{telefon}}"
  email_c="{{email}}"
  nerezident="0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="mfp:anaf:dgti:d212:declaratie:v11"
  xmlns="mfp:anaf:dgti:d212:declaratie:v11">
{{oblig_realizat_block}}
{{cap14_blocks}}
</d212>
```

- [ ] **Step 2: Write `oblig_realizat.xml`**

```xml
<oblig_realizat
  cass_ven_dpi="{{cass_ven_dpi|default:0}}"
  cass_ven_asc="{{cass_ven_asc|default:0}}"
  cass_ven_cfb="{{cass_ven_cfb|default:0}}"
  cass_ven_inv="{{cass_ven_inv}}"
  cass_ven_asp="{{cass_ven_asp|default:0}}"
  cass_ven_alt="{{cass_ven_alt|default:0}}"
  cass_total_ven="{{cass_total_ven}}"
  cass_baza="{{cass_baza}}"
  cass_anuala="{{cass_anuala}}"
  cass_datorat_art180="{{cass_datorat_art180|default:0}}"
  cass_datorat="{{cass_datorat}}"
  cass_retinut="{{cass_retinut}}"
  cass_dif_plus="{{cass_dif_plus}}"
  cass_dif_minus="{{cass_dif_minus}}"
  bifa_cass_real="{{bifa_cass_real}}"
  bifa_cass_datorat_dpi="{{bifa_cass_datorat_dpi|default:0}}"
  bifa_cass_datorat_ai="{{bifa_cass_datorat_ai|default:0}}"
  oblimpoz_real_total="{{oblimpoz_real_total}}"
  oblimpoz_real_dif_deplata="{{oblimpoz_real_dif_deplata}}"
  oblimpoz_real_dif_restituit="{{oblimpoz_real_dif_restituit}}"
  oblcas_real_difPlus="{{oblcas_real_difPlus|default:0}}"
  oblcas_real_str="{{oblcas_real_str|default:0}}"
  oblcass_real_difMinus_174="{{oblcass_real_difMinus_174|default:0}}"
  oblcass_real_difPlus_dpi="{{oblcass_real_difPlus_dpi|default:0}}"
  oblcass_real_difMinus_dpi="{{oblcass_real_difMinus_dpi|default:0}}"
  oblcass_real_str="{{oblcass_real_str_dup|default:0}}"
  oblcass_real_str_pensie="{{oblcass_real_str_pensie|default:0}}"
  impozit_venit_plus="{{impozit_venit_plus}}"
  impozit_venit_minus="{{impozit_venit_minus|default:0}}"
  cas_plus="{{cas_plus|default:0}}"
  cass_plus="{{cass_plus}}"
  cass_minus="{{cass_minus|default:0}}"
  dif_de_plata="{{dif_de_plata}}"
  dif_de_restituit="{{dif_de_restituit|default:0}}" />
```

- [ ] **Step 3: Write `cap14-strainatate.xml`**

```xml
<cap14
  str_stat_realiz_v="{{stat_iso}}"
  den_stat="{{stat_denumire}}"
  str_categ_venit="{{cod_categorie}}"
  den_categ_venit="{{denumire_categorie}}"{{#if dubla_impunere}}
  dubla_impunere="{{dubla_impunere}}"{{/if}}
  str_venit_net_anual="{{venit_net_anual}}"{{#if pierdere_precedenta}}
  str_pierdere_precedenta="{{pierdere_precedenta}}"{{/if}}
  str_pierdere_compensata="{{pierdere_compensata|default:0}}"
  str_venit_recalculat="{{venit_recalculat}}"
  str_impozit_datorat_Ro="{{impozit_datorat_ro}}"{{#if impozit_platit}}
  str_impozit_platit="{{impozit_platit}}"{{/if}}
  str_credit_fiscal="{{credit_fiscal|default:0}}"
  str_dif_impozit_datorat="{{dif_impozit_datorat}}" />
```

- [ ] **Step 4: Write `cap14-romania.xml`**

```xml
<cap14
  str_categ_venit="{{cod_categorie}}"
  den_categ_venit="{{denumire_categorie}}"
  str_venit_net_anual="{{venit_net_anual}}"
  str_pierdere_compensata="{{pierdere_compensata|default:0}}"
  str_venit_recalculat="{{venit_recalculat}}"
  str_impozit_datorat_Ro="{{impozit_datorat_ro}}"
  str_credit_fiscal="{{credit_fiscal|default:0}}"
  str_dif_impozit_datorat="{{dif_impozit_datorat}}" />
```

- [ ] **Step 5: XML well-formedness sanity check**

Skill consumes these templates with parametrii. Templates THEMSELVES (with `{{...}}` placeholders) are not valid XML standalone — the test is just shape inspection by eye. To verify the structure after parameter substitution would be valid, do a quick instantiation test:

```bash
python3 - <<'PY'
import re, pathlib, xml.etree.ElementTree as ET
templates = pathlib.Path("claude/skills/declaratia-unica-romania/schema/templates")
for t in templates.glob("*.xml"):
    raw = t.read_text()
    # naïve placeholder strip for sanity check only
    stripped = re.sub(r"\{\{[^}]+\}\}", "0", raw)
    stripped = re.sub(r"\{\{#if[^}]+\}\}", "", stripped)
    stripped = stripped.replace("{{/if}}", "")
    try:
        ET.fromstring(stripped)
        print(f"OK {t.name}")
    except ET.ParseError as e:
        print(f"FAIL {t.name}: {e}")
PY
```

Expected: 4 "OK" lines for d212-root.xml, oblig_realizat.xml, cap14-strainatate.xml, cap14-romania.xml. If d212-root fails because `{{oblig_realizat_block}}` and `{{cap14_blocks}}` become text content not element — that's expected (substitution at render time inserts real elements). Accept "FAIL d212-root.xml" with text-content note; the substitution model is documented in `form-mapping.md`.

If templates fail for unexpected reasons (malformed attributes, unclosed tags), fix and re-run.

- [ ] **Step 6: Commit**

```bash
git add claude/skills/declaratia-unica-romania/schema/templates/
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add XML templates for D212 generation

d212-root.xml, oblig_realizat.xml, cap14-strainatate.xml, cap14-romania.xml
with {{placeholders}} for parameter substitution. Templates mirror the
golden 2025 D212.xml structure exactly; placeholders correspond 1:1 to
form-mapping.yaml field names.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Workflow Protocols

### Task 3.1: `workflow/freshness-check.md`

**Files:**
- Create: `claude/skills/declaratia-unica-romania/workflow/freshness-check.md`

- [ ] **Step 1: Write the protocol**

```markdown
# Freshness check protocol

Rulează la Faza 2 a sesiunii. Verifică dacă cunoștințele statice ale skill-ului (schema XML, structura DUF) sunt actuale.

## Trigger

Citește frontmatter din:
- `schema/d212-xml-schema.md`
- `schema/duf-platform-structure.md`

Pentru fiecare, calculează `today - last_verified`.

- **< 30 zile** → skip, continuă cu Faza 3.
- **≥ 30 zile** → rulează verificarea.

## Procedură

1. **Fetch DUF.** Cere `https://www.anaf.ro/declaratii/duf` (WebFetch sau echivalent).

2. **Extrage `platform_version`.** E în footer-ul paginii, format `V-x.y.z / DD.MM.YYYY`.

3. **Extrage lista secțiunilor.** Trebuie să fie cele 5 secțiuni cunoscute (Date identificare, Venituri realizate, Venituri cu reținere la sursă, CAS, CASS) plus butoanele "Adaugă venit străinătate/România".

4. **Compară cu frontmatter:**

   | Caz | Acțiune |
   |---|---|
   | `platform_version` identic | bump `last_verified` în ambele frontmatter-uri la today; commit + `_sync.sh pull <agent>` |
   | Patch version diferit (V-1.8.08 → V-1.8.09) | (a) fetch din nou Instrucțiuni PDF anuale; (b) confirmă că coduri categorie 2012/2017/2018 + atributele cap14 + atributele oblig_realizat sunt neschimbate; (c) update `platform_version` și `last_verified`; (d) commit + sync |
   | Minor diferit (V-1.8.x → V-1.9.x) | hard-stop. Notifică user: "Schema DUF s-a schimbat de la V-1.8.x la V-1.9.x. Trebuie audit manual al `form-mapping.yaml`, `form-mapping.md`, și template-urilor XML." Cere user confirmation să pornească o sub-sarcină de update; nu continuă sesiunea curentă. |
   | Major sau namespace diferit | hard-stop. Update manual obligatoriu pentru toate fișierele schema/ și template-urile. |
   | Lista secțiunilor sau butoanelor schimbată | hard-stop. Update `duf-platform-structure.md` cu noile valori înainte de a continua. |

5. **După update reușit:**
   - `git add claude/skills/declaratia-unica-romania/schema/`
   - `git commit -m "declaratia-unica-romania: refresh schema after DUF version bump"`
   - `_sync.sh pull <agent>` (presupunând că modificarea s-a făcut în install dir runtime; vezi `../_sync.sh` pentru sub-comenzi)
   - Anunță user: "Schema actualizată la V-x.y.z. Continuă sesiunea."

## Loguri

Toate verificările (skip sau update) se înregistrează în `worklog.md` din sesiunea curentă, cu format:

```
[YYYY-MM-DD HH:MM] freshness-check: schema last_verified=YYYY-MM-DD, age=N days, action=skip|update, platform_version_old=Vx.y.z, platform_version_new=Vx.y.z
```
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/declaratia-unica-romania/workflow/freshness-check.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add schema freshness check protocol

Phase 2 gate: read schema frontmatter, fetch DUF, compare platform_version
and section list. Patch versions → auto-update + sync. Minor/major/
namespace → hard-stop, prompt user for manual audit. All checks logged
to session worklog.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.2: `workflow/preflight.md`

**Files:**
- Create: `claude/skills/declaratia-unica-romania/workflow/preflight.md`

- [ ] **Step 1: Write the protocol**

```markdown
# Preflight protocol

Faza 4 a sesiunii. Verifică prezența documentelor obligatorii în `{an_fiscal}/sesiuni/{slug}/inputs/` înainte de calcul.

## Procedură

1. **Determină lista documentelor obligatorii** pe baza scenariilor selectate la Faza 1:

   - **PF investiții** → vezi `../pf-investitii.md#documente-necesare` pentru lista exactă per sub-scenariu (IBKR, broker RO, bancă RO pentru dobânzi, dovezi cripto).
   - **PFA real** → vezi `../pfa-real.md#documente-necesare`.
   - **Combinat** → uniunea ambelor liste.

2. **Listează conținutul `inputs/`** prin `ls -la {an_fiscal}/sesiuni/{slug}/inputs/`.

3. **Verifică match prin glob patterns** definit în fiecare scenario file. Examplu:
   - PF investiții IBKR: glob `annual_activity_statement*.pdf` SAU `*.csv` cu nume IBKR
   - Dividende RO: glob `hotarare*AGA*.pdf` SAU `nota*plata*dividende*.pdf`

4. **Pentru fiecare document lipsă**, listează:
   - Numele tipului de document (ex. "raport anual IBKR")
   - Patternul de fișier așteptat (ex. `annual_activity_statement_*.pdf`)
   - Sursa de unde se obține (URL + secțiune)
   - De ce e necesar (un rând)

5. **Hard-stop** până una din:
   - User pune fișierele în `inputs/` și agentul re-rulează preflight (`ls` din nou)
   - User scrie waiver explicit: "Nu am {document}, e OK pentru că {motiv}". Waiverul se înregistrează în `worklog.md` cu timestamp și motivul verbatim.

6. **Output preflight pass:** entry în `worklog.md`:
   ```
   [YYYY-MM-DD HH:MM] preflight: PASS, documents={count}, waivers={count}
   ```

## Format prompt user la documente lipsă

```
Lipsesc următoarele documente în inputs/. Te rog să le pui acolo, sau să confirmi waiver:

1. **Raport anual IBKR** (pattern: `annual_activity_statement_*.pdf`)
   Obtii din: IBKR Client Portal → Reports → Activity → Annual Activity Statement (PDF)
   Necesar pentru: calcul câștig capital (cap 2012) și dividende (cap 2018)

2. **Dovadă reținere impozit dividende străinătate** (pattern: `*.f1042S.pdf` sau echivalent)
   Obtii din: IBKR Client Portal → Reports → Tax Documents → 1042-S
   Necesar pentru: completarea `str_impozit_platit` la cap 2018 + credit fiscal

[etc.]

Spune când ai pus fișierele, sau scrie "waiver: nu am X pentru că Y" pentru fiecare lipsă acceptabilă.
```

## Reguli stricte (gate enforcement)

- Nu se calculează nimic înainte de preflight PASS.
- Nu se folosesc valori default sau zero implicit pentru documente lipsă.
- "Estimează" nu e o opțiune — fie ai sursa, fie ai waiver documentat.
- Skill-ul nu sugerează vreodată să sari peste preflight pentru "rapiditate".
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/declaratia-unica-romania/workflow/preflight.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add preflight documents gate

Phase 4 gate: enumerate required docs per scenario, glob inputs/, hard-stop
on missing without explicit user waiver logged with reason. No silent
defaults, no estimation shortcuts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.3: `workflow/citation-protocol.md`

**Files:**
- Create: `claude/skills/declaratia-unica-romania/workflow/citation-protocol.md`

- [ ] **Step 1: Write the protocol**

```markdown
# Citation protocol

Disciplina de citare pentru orice fapt fiscal folosit în calcul.

## Whitelist surse (recap din spec)

**Primare (citare directă acceptată):**
- `anaf.ro` — inclusiv `/declaratii/duf`, `/declaratii_R/*`, Instrucțiuni PDF, Broșură PDF, comunicate
- `mfinante.gov.ro` / `mfp.gov.ro`
- `monitoruloficial.ro`
- `legislatie.just.ro`
- `bnr.ro`

**Secundare (navigare/index, nu citare):**
- `static.anaf.ro`
- `cdep.ro`
- `cursbnr.ro` — convenience pentru media anuală V2

**Refuzate:**
- Reddit, Avocatnet, GoldRing, contzilla, forumuri
- Profit.ro, HotNews, Capital.ro, Ziarul Financiar, alte știri
- Bloguri contabili individuali, agregatoare neoficiale
- Memoria din training a agentului

## Format frontmatter pe modulele cache

Fiecare fișier din `_legi/{an}/*.md` (cu excepția README.md) începe cu:

```yaml
---
fapt: <nume_fapt_unic>           # ex. cota_impozit_dividende
valoare: <valoarea numerică sau string scurt>
articol: <articol legal>          # ex. "Codul Fiscal art. 97 alin. (7)"
source_url: <URL whitelist>
source_type: <pdf-oficial | pagina-oficiala | monitor-oficial>
accessed_on: <YYYY-MM-DD>
last_verified: <YYYY-MM-DD>
citat_verbatim: |
  <citat ≥ 1 propoziție, păstrat exact ca în sursă>
---
```

Body-ul (după frontmatter) conține:
- **Ancore markdown** (`# Cota`, `# Plafon`, etc.) la care fac referință cache_ref din `form-mapping.yaml`
- **Context** (de ce e relevant)
- **Exemple** dacă ajută

## Format citare în worklog și raport

Pentru fiecare valoare numerică, ancoră inline `[descriere: cache_path#anchor]`:

```
câștig capital total cap 2012: 13.105 RON
  [cota 10%: _legi/2025/impozit-castig-capital.md#cota-art-94]
  [agregare anuală FIFO: _legi/2025/impozit-castig-capital.md#regula-anuala-broker-international]
  [conversie V2 USD→RON: _legi/2025/curs-bnr-mediu.md (USD=4.6612)]
  [V2 advisory: _legi/2025/curs-bnr-mediu.md#avertisment-vs-per-tranzactie]
```

## Anti-halucinare

Agentul aplică următoarele reguli:

1. **Nu folosi cunoștințe din training** ca sursă autoritativă, niciodată. Cunoștințele din training sunt utile pentru navigare ("știu unde să caut") dar NU pentru citare ("articolul X spune Y").

2. **Lipsește un fapt** → trei pași:
   a. Caută în `_legi/{an}/`
   b. Lipsește acolo → fetch din whitelist (anaf.ro Instrucțiuni PDF, legislatie.just.ro Codul Fiscal, monitoruloficial.ro pentru OUG-uri/ordine)
   c. Whitelist nu acoperă → întreabă user

3. **User citează sursă refuzată** (Reddit, blog, etc.) → agent refuză:
   ```
   Sursa X (Reddit/blog/știre) nu e acceptată ca sursă autoritativă conform
   whitelist-ului. Pot să verific aceeași afirmație din [sursa primară
   relevantă, ex. Codul Fiscal art. Y]?
   ```

4. **User cere skip citation** ("știi tu, hai mai repede") → agent refuză:
   ```
   Skill-ul cere citare pentru fiecare valoare numerică, ca audit trail.
   Continui cu citarea — durează ~30 secunde să fetch din cache. Dacă
   cache-ul lipsește, intru în re-verificare scurtă.
   ```

## Loguri

Fiecare fetch nou (sau re-fetch) se înregistrează în `worklog.md`:

```
[YYYY-MM-DD HH:MM] fetch: source_url=<URL>, fapt=<nume>, status=<200|404|...>, cached_to=<path>
```
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/declaratia-unica-romania/workflow/citation-protocol.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add citation protocol

Whitelist enforcement, frontmatter format for legi cache modules, inline
citation format for worklog and raport, anti-hallucination rules (no
training memory as authoritative, refuse refused sources, refuse skip
citation pressure).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.4: `workflow/currency-conversion.md`

**Files:**
- Create: `claude/skills/declaratia-unica-romania/workflow/currency-conversion.md`

- [ ] **Step 1: Write the protocol**

```markdown
# Currency conversion protocol — V2 (media anuală cu cross-check BNR)

Strategia confirmată: **V2 — media anuală pe totaluri** prin `cursbnr.ro/curs-valutar-mediu`, cu cross-check 3-puncte împotriva arhivei BNR.

## Aplicabilitate

- Aplică pentru: venituri în valută (USD, EUR, GBP, etc.) de la brokeri internaționali, conturi străinătate, obligațiuni străinătate, dividende străinătate.
- **NU aplică** pentru: venituri deja în RON (Tradeville/BVB, dobânzi bănci RO, dividende companii RO). Cursul = 1.0.

## Procedura anuală

La Faza 3 (cache check), pentru fiecare an fiscal nou sau cache `curs-bnr-mediu.md` cu `last_verified > 90 zile`:

1. **Fetch cursbnr.ro:** `https://www.cursbnr.ro/curs-valutar-mediu` (filtrează pentru anul fiscal). Extrage valorile pentru USD, EUR (și alte valute dacă sesiunea le cere).

2. **Fetch BNR sample** — 3 cursuri spot din `bnr.ro` (sau API-ul BNR XML):
   - 15 ianuarie {an}
   - 15 iunie {an}
   - 15 decembrie {an}
   
   Dacă o dată e weekend, ia ziua lucrătoare imediat anterioară.

3. **Recalculează media simplă a celor 3** pentru fiecare valută:
   ```
   media_3 = (curs_jan + curs_iun + curs_dec) / 3
   ```

4. **Comparare cu valoarea cursbnr.ro:**
   ```
   delta_pct = abs(media_anuala_cursbnr - media_3) / media_3 * 100
   ```
   - `delta_pct < 0.5%` → accept, scrie în cache
   - `delta_pct >= 0.5%` → hard-stop. Întreabă user:
     ```
     Discrepanță conversie {valuta} pentru anul {an}:
     - cursbnr.ro media anuală: {X}
     - BNR sample (3 puncte) media: {Y}
     - delta: {delta_pct}%
     
     Vreți să folosesc media BNR sample, valoarea cursbnr.ro, sau să cer
     arhiva BNR completă pentru calcul exact?
     ```

5. **Scrie `_legi/{an}/curs-bnr-mediu.md`** cu frontmatter complet:

   ```yaml
   ---
   fapt: curs_valutar_mediu_anual
   valori:
     USD: 4.6612
     EUR: 4.9745
   sursa_primara_url: https://www.bnr.ro/Cursul-de-schimb-3544.aspx
   sursa_convenience_url: https://www.cursbnr.ro/curs-valutar-mediu
   accessed_on: 2026-05-11
   last_verified: 2026-05-11
   verification_method: sample_3_dates_BNR
   verification_status: match    # sau mismatch (cu detalii)
   sample_BNR:
     USD: [4.5500, 4.6700, 4.7800]
     EUR: [4.9200, 4.9700, 5.0400]
   citat_verbatim: |
     (Cursul oficial BNR per data — preluat din arhiva publică. Media anuală
     calculată ca medie aritmetică simplă a tuturor cursurilor publicate în
     zilele lucrătoare ale anului fiscal.)
   ---
   
   # Avertisment vs per-tranzacție
   
   Această sesiune folosește **V2 — media anuală pe totaluri**, nu per-tranzacție.
   Codul Fiscal art. 76 alin. (2) prevede curs BNR la data realizării venitului
   (per-tranzacție). În practica ANAF, media anuală e tolerată pentru sume mici;
   pentru volume mari sau control fiscal, divergența poate fi discutabilă.
   
   În `raport-completare.md` din sesiunea curentă, secțiunea **"Avertismente"**
   menționează explicit această divergență.
   ```

## Aplicare în calcul

Pentru fiecare sumă în valută din inputs broker:

```
suma_RON = round(suma_VALUTA * curs_valuta)
```

unde `curs_valuta` se citește din `_legi/{an}/curs-bnr-mediu.md` (atributul `valori.VALUTA` din frontmatter).

## Loguri

Fiecare conversie aplicată în calcul se înregistrează în `worklog.md`:

```
[YYYY-MM-DD HH:MM] currency-convert: 1.234,56 USD * 4.6612 = 5.755 RON (cap 2012, broker IBKR)
```
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/declaratia-unica-romania/workflow/currency-conversion.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add V2 currency conversion protocol

cursbnr.ro as convenience source + 3-point BNR sample cross-check; ≥0.5%
delta triggers hard-stop with user prompt; cache file frontmatter
includes verification status, sample dates, and the mandatory V2-vs-
per-tx advisory note.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.5: `legi-cache.md` — cache management overview

**Files:**
- Create: `claude/skills/declaratia-unica-romania/legi-cache.md`

- [ ] **Step 1: Write the cache management doc**

```markdown
# Legi cache management

Cache-ul de legi (fapte fiscale) trăiește **OUT-OF-REPO**, în:

```
/Users/trocaneduard/Documents/Personal/declaratii-unice/_legi/{an_fiscal}/
```

Asta separă date personale de skill-ul versionat și permite re-verificarea anuală fără să atingem repo-ul.

## Structură (G3 — index + module)

```
_legi/{an}/
├── README.md                          # index sintetic + last_verified per modul
├── salariu-minim.md
├── plafoane-cass.md
├── plafoane-cas.md
├── impozit-dividende.md
├── impozit-castig-capital.md
├── impozit-dobanzi.md
├── impozit-cripto.md
├── pfa-real-cheltuieli.md
├── tratate-dubla-impunere.md
├── curs-bnr-mediu.md
└── modificari-cf-fata-de-anul-precedent.md
```

Toate au frontmatter conform `workflow/citation-protocol.md`.

## README.md — index sintetic

Format:

```markdown
# Cache legi — anul fiscal {an}

| Fapt | Valoare scurtă | Modul | last_verified |
|---|---|---|---|
| Salariu minim brut | 4.050 RON | [salariu-minim.md](salariu-minim.md) | 2026-05-11 |
| Plafon CASS (12 × salariu_min) | 97.200 RON | [plafoane-cass.md](plafoane-cass.md) | 2026-05-11 |
| Cotă CASS | 10% | [plafoane-cass.md](plafoane-cass.md) | 2026-05-11 |
| Cotă impozit dividende RO | 8% | [impozit-dividende.md](impozit-dividende.md) | 2026-05-11 |
| Cotă impozit câștig capital | 10% / 1% (după caz) | [impozit-castig-capital.md](impozit-castig-capital.md) | 2026-05-11 |
| Cotă impozit dobânzi | 10% | [impozit-dobanzi.md](impozit-dobanzi.md) | 2026-05-11 |
| Curs mediu USD | 4.6612 | [curs-bnr-mediu.md](curs-bnr-mediu.md) | 2026-05-11 |
| Curs mediu EUR | 4.9745 | [curs-bnr-mediu.md](curs-bnr-mediu.md) | 2026-05-11 |

## Modificări CF față de anul precedent

Vezi [modificari-cf-fata-de-anul-precedent.md](modificari-cf-fata-de-anul-precedent.md) pentru changelog.

## Reverificare

Fiecare modul are `last_verified` în frontmatter. Trigger refresh:
- Folder lipsă pentru anul fiscal → refresh complet
- `last_verified > 90 zile` la un modul → refresh modul-by-modul
```

## Procedura de re-verificare modul

Pentru un modul stale (`last_verified > 90 zile` sau lipsă):

1. Citește `source_url` din frontmatter (sau, dacă modul nou, determină din whitelist + Instrucțiuni PDF anuale).
2. Fetch URL.
3. Extrage valoarea curentă a faptului + citat verbatim minim 1 propoziție.
4. Update frontmatter: `valoare`, `accessed_on`, `last_verified`, `citat_verbatim`.
5. Update body cu context dacă s-a schimbat.
6. Update entry în `README.md`.
7. Înregistrează în `worklog.md`:
   ```
   [YYYY-MM-DD HH:MM] legi-refresh: module=impozit-dividende.md, old_value=X%, new_value=Y%, source_url=...
   ```

## Versiunile istorice (dacă valoarea s-a schimbat semnificativ)

Dacă o reverificare descoperă schimbare materială (ex. cota dividende 5% → 8% în 2024), păstrăm istoricul:

```
_legi/2024/impozit-dividende.md         # cota 5% (anul fiscal 2024)
_legi/2025/impozit-dividende.md         # cota 8% (anul fiscal 2025)
```

Cache-ul e per-an fiscal, deci natural separat — nu folosim sufix `.v2` pe același an decât dacă există o rectificativă ANAF intra-anuală.

## Modulele relevante per scenariu

Indicat în `pf-investitii.md` și `pfa-real.md`, dar recap:

- **PF investiții**: `impozit-dividende`, `impozit-castig-capital`, `impozit-dobanzi`, `impozit-cripto`, `tratate-dubla-impunere`, `curs-bnr-mediu`, `plafoane-cass`, `salariu-minim`.
- **PFA real**: `pfa-real-cheltuieli`, `plafoane-cas`, `plafoane-cass`, `salariu-minim`, `modificari-cf-fata-de-anul-precedent`.
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/declaratia-unica-romania/legi-cache.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: document legi cache management

Out-of-repo location, G3 module structure, README.md index format,
per-module refresh procedure with worklog logging, scenario-to-module
mapping. Versioning is per fiscal year, not per file suffix.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — Orchestrator + SKILL.md

### Task 4.1: `orchestrator.md` — full workflow

**Files:**
- Create: `claude/skills/declaratia-unica-romania/orchestrator.md`

- [ ] **Step 1: Write the orchestrator**

```markdown
# Orchestrator — Declarația Unică România

Documentul descrie cele 8 faze ale workflow-ului, fiecare cu hard-gate. Acest fișier e citit imediat după `SKILL.md` la începutul oricărei sesiuni.

## Definiții

- **Hard-gate**: agentul NU execută acțiuni din faza următoare până condiția gate-ului curent nu e satisfăcută explicit. Nu există fallback tăcut, default-uri implicite sau "presupun că e OK". La blocaj: agent listează ce lipsește și așteaptă input.
- **Ultima sesiune detectabilă**: cel mai recent folder cu format `YYYY-MM-DD_*` găsit în `declaratii-unice/*/sesiuni/`, indiferent de an fiscal.

## Phase 1 — Identificare sesiune

**Gate:** persoană + an fiscal + scenarii confirmate; folder sesiune creat.

Întrebări obligatorii (în această ordine):

1. "Pentru cine completezi declarația? (default: pentru tine — Eduard Trocan)"
   - Dacă self: `persoana_slug = eduard-trocan`
   - Altcineva: cere nume complet, slugifică (lowercase, înlocuiește spații cu `-`, elimină diacritice)

2. "Care e anul fiscal declarat? (default: anul calendaristic precedent — {YYYY-1})"
   - Anul fiscal = anul ale cărui venituri se declară (ex. 2025 pentru declarația depusă în 2026)

3. "Ce scenarii rulăm? (PF investiții / PFA real / ambele)"
   - PF investiții — dividende, câștig capital, dobânzi, cripto, alte instrumente financiare
   - PFA real — venit PFA în sistem real (NU norma de venit)
   - Ambele — output unificat

**Acțiuni la pass:**
- Creează `/Users/trocaneduard/Documents/Personal/declaratii-unice/{an_fiscal}/sesiuni/{YYYY-MM-DD}_{persoana_slug}/` cu subfoldere `inputs/` și `outputs/`.
- Creează `worklog.md` în folderul sesiunii cu primul entry:
  ```
  [YYYY-MM-DD HH:MM] session-start: persoana=<slug>, an_fiscal=<an>, scenarii=<list>, agent=<claude|codex>
  ```
- Confirmă cu user creearea, listează path-ul.

## Phase 2 — Freshness check schema

**Gate:** `schema/*.md` au `last_verified < 30 zile` (skip) SAU au fost actualizate față de DUF live (update + sync).

Procedură: vezi `workflow/freshness-check.md`.

Hard-stop pe minor/major/namespace change → notifică user, oprește sesiunea curentă, propune sub-sarcină de audit.

## Phase 3 — Cache legi check

**Gate:** modulele relevante scenariilor au `last_verified < 90 zile`.

Pentru fiecare scenariu activ:

- **PF investiții** → verifică `_legi/{an}/{impozit-dividende,impozit-castig-capital,impozit-dobanzi,impozit-cripto,tratate-dubla-impunere,curs-bnr-mediu,plafoane-cass,salariu-minim}.md`.
- **PFA real** → verifică `_legi/{an}/{pfa-real-cheltuieli,plafoane-cas,plafoane-cass,salariu-minim,modificari-cf-fata-de-anul-precedent}.md`.

Folder `_legi/{an}/` lipsă → refresh complet (toate modulele scenariului). Pentru cursul valutar V2: folosește `workflow/currency-conversion.md`.

La pass, log:
```
[YYYY-MM-DD HH:MM] cache-check: scenario=<>, modules_verified=<count>, refreshed=<count>
```

## Phase 4 — Preflight documente

**Gate:** toate documentele obligatorii sunt prezente în `inputs/` SAU au waiver documentat.

Procedură: vezi `workflow/preflight.md`. Lista per scenariu e în `pf-investitii.md` / `pfa-real.md`.

Hard-stop până PASS.

## Phase 5 — Calcul + citare

**Gate:** worklog conține câte un entry pentru fiecare linie cap14 + oblig_realizat cu raw / cite / computed.

Pentru fiecare scenariu, urmează procedura din scenariu file (`pf-investitii.md#proceduri-calcul` sau `pfa-real.md#proceduri-calcul`). Disciplina de citare: vezi `workflow/citation-protocol.md`.

Conversie valutară: `workflow/currency-conversion.md`.

La pass, log:
```
[YYYY-MM-DD HH:MM] calculations-done: cap14_lines=<count>, total_dif_de_plata=<RON>, total_dif_de_restituit=<RON>
```

## Phase 6 — Generare output

**Gate:** `outputs/D212.xml` generat și validat structural; `outputs/raport-completare.md` complet.

Procedură generare XML:
1. Citește `schema/templates/d212-root.xml` ca shell.
2. Instanțiază `oblig_realizat.xml` cu valorile din `<oblig_realizat>` calculate la Faza 5.
3. Pentru fiecare linie cap14, instanțiază `cap14-strainatate.xml` sau `cap14-romania.xml`.
4. Substituie placeholderii `{{...}}` cu valori reale; gestionează `{{#if X}}...{{/if}}` ca render condițional.
5. Concatenează în `d212-root.xml` substituind `{{oblig_realizat_block}}` și `{{cap14_blocks}}`.
6. Scrie `outputs/D212.xml`.

Validare structurală:
```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('outputs/D212.xml'); print('XML valid')"
```

Hard-stop pe eroare.

Procedură generare raport: vezi structura fixă din spec Secțiunea 5.2 (frontmatter, sumar, detalii per categorie, instrucțiuni completare DUF, surse, avertismente).

## Phase 7 — Review utilizator

**Gate:** user răspunde "OK" sau cere corecție.

Prezintă summary:
```
Sesiunea pentru {persoana}, an fiscal {an}, scenarii {list}.

Sumar fiscal:
- Impozit pe venit total: {X} RON
- CAS total: {Y} RON
- CASS total: {Z} RON
- Diferență de plată / restituit: {W} RON

Detalii complete: outputs/raport-completare.md
XML pentru import DUF: outputs/D212.xml

Vrei să revizuim ceva specific sau confirmi sesiunea?
```

Așteaptă răspuns. Corecție → întoarcere la Phase 5 cu modificarea înregistrată în worklog. OK → Phase 8.

## Phase 8 — Închidere sesiune

Log final în worklog:
```
[YYYY-MM-DD HH:MM] session-close: status=OK, outputs_path=<>, dif_de_plata=<RON>
```

Anunță user:
```
Sesiunea închisă. Artefacte salvate la:
- {an}/sesiuni/{slug}/outputs/D212.xml
- {an}/sesiuni/{slug}/outputs/raport-completare.md
- {an}/sesiuni/{slug}/worklog.md

Pași următori pentru tine:
1. Citește `raport-completare.md` și verifică sumarul fiscal.
2. Importă `D212.xml` în https://www.anaf.ro/declaratii/duf (sau completează manual urmând secțiunea "Instrucțiuni completare manuală" din raport).
3. Submit electronic prin SPV cu certificat / credențiale.
4. Plătește diferența la cont ANAF (vezi instrucțiuni anuale pentru cont destinație).
```
```

- [ ] **Step 2: Commit**

```bash
git add claude/skills/declaratia-unica-romania/orchestrator.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add 8-phase orchestrator

Phase 1 session setup → 2 schema freshness → 3 cache legi → 4 preflight
docs → 5 calc+cite → 6 generate XML + raport → 7 user review → 8 close.
Each phase has explicit hard-gate definition and worklog log format.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.2: `SKILL.md` — compact entry point

**Files:**
- Create: `claude/skills/declaratia-unica-romania/SKILL.md`

- [ ] **Step 1: Write the SKILL.md**

```markdown
---
name: declaratia-unica-romania
description: Use when the user wants to fill the Romanian annual income tax Declarația Unică (D212) — phrases like "completare declarație unică", "D212", "declaratia unica", venituri din dividende, venituri PFA, câștig capital broker IBKR/Tradeville, venituri investiții ANAF. Covers Persoană Fizică (dividends, capital gains, crypto, interest from RO and foreign brokers) and PFA în sistem real. Do not use for: PFA cu norma de venit, microîntreprinderi/SRL, venituri salariale, venituri din chirii, asistență la control fiscal.
---

# Declarația Unică România

## Overview

Skill orchestrator pentru completarea anuală a D212 cu **disciplină strictă de citare** din surse oficiale (ANAF, MF, Monitor Oficial, Codul Fiscal) și separare clară între cunoștințe statice (skill) și fapte anuale (cache local). Skill-ul refuză surse neoficiale, refuză să inventeze fapte fiscale și emite **un XML importabil în duf.anaf.ro** + **un raport markdown auditabil**.

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

3. **Mirror sync**: orice modificare la fișiere skill se oglindește în `~/.{claude,codex}/skills/declaratia-unica-romania/` prin `_sync.sh`. Vezi `_sync.sh --help`.

4. **Conversie valutară V2**: cursbnr.ro media anuală + cross-check BNR 3-puncte. Notă obligatorie în raport: "V2 vs per-tranzacție Cod Fiscal art. 76 alin. (2)". Vezi `workflow/currency-conversion.md`.

## Limba

Toată comunicarea cu utilizatorul, fișierele cache, raportul final și instrucțiunile sunt în **română**. Numele coduri categorie și atributelor XML rămân ca în sursa oficială.

## Locații

- Cache legi: `/Users/trocaneduard/Documents/Personal/declaratii-unice/_legi/{an}/`
- Sesiuni: `/Users/trocaneduard/Documents/Personal/declaratii-unice/{an_fiscal}/sesiuni/{date}_{persoana}/`
- Skill repo: `/Users/trocaneduard/Documents/Personal/ai-skills/{claude,codex}/skills/declaratia-unica-romania/`
- Install dirs: `~/.{claude,codex}/skills/declaratia-unica-romania/`
```

- [ ] **Step 2: Word count check**

Run: `wc -w claude/skills/declaratia-unica-romania/SKILL.md`

Expected: under 500 words (frequently-loaded skills target). If over, trim — move details to `orchestrator.md`.

- [ ] **Step 3: Sync to install dirs**

```bash
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh push
```

Expected: 2 "synced:" lines, both install dirs now mirror the repo.

Verify:
```bash
test -f ~/.claude/skills/declaratia-unica-romania/SKILL.md && echo "claude install OK"
test -f ~/.codex/skills/declaratia-unica-romania/SKILL.md && echo "codex install OK"
```

Expected: 2 OK lines.

- [ ] **Step 4: Mirror to codex base in repo**

```bash
AI_SKILLS_REPO="$(pwd)" rsync -a --delete --exclude=".gitkeep" \
  claude/skills/declaratia-unica-romania/ \
  codex/skills/declaratia-unica-romania/
```

(Or copy specific files if rsync would clobber. For now, codex/skills/declaratia-unica-romania/ should be byte-identical to claude/skills/declaratia-unica-romania/ — repo rule.)

- [ ] **Step 5: Commit**

```bash
git add claude/skills/declaratia-unica-romania/ codex/skills/declaratia-unica-romania/
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add SKILL.md entry point

Compact orchestrator stub (<500 words): description with RO trigger
phrases, 8-phase reference, scenario routing, non-negotiable disciplines
(whitelist, citation, sync, V2 conversion). Mirrored to codex/skills/
and pushed to both install dirs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5 — Per-scenario Files

### Task 5.1: `pf-investitii.md` — PF investiții scenario

**Files:**
- Create: `claude/skills/declaratia-unica-romania/pf-investitii.md`

- [ ] **Step 1: Write the scenario**

```markdown
# Scenariu PF — Venituri din investiții și instrumente financiare

Acoperă: dividende, câștig capital (acțiuni, ETF-uri, cripto, derivate), dobânzi (conturi de economii, depozite, obligațiuni).

## Documente necesare

### Brokeri internaționali (Interactive Brokers — IBKR)

| Document | Pattern fișier | Sursă | Necesar pentru |
|---|---|---|---|
| Raport anual de activitate | `annual_activity_statement*.pdf` | IBKR Client Portal → Reports → Activity → Annual | Câștig capital cap 2012, dividende cap 2018 |
| Raport tranzacții CSV | `*statement*.csv` sau `ibkr*.csv` | IBKR Client Portal → Reports → Trade Confirmation Flex | Detaliu FIFO câștig capital |
| Raport dividende HTML | `*dividends*.html` | IBKR Client Portal → Reports → Statements | Listă dividende cu gross/withholding |
| Form 1042-S | `*f1042*S*.pdf` | IBKR Client Portal → Reports → Tax Documents | Impozit reținut străinătate dividende |
| Raport curs valutar broker | `*fx*.pdf` | IBKR Client Portal → Reports → Currency Conversion | Cross-check conversii valutare |

### Brokeri RO (Tradeville, BT Capital Partners, etc.)

| Document | Pattern fișier | Necesar pentru |
|---|---|---|
| Raport fiscal anual | `*fiscal*RO*.pdf` sau echivalent | Câștig capital cap 2012 RO (de obicei deja taxat la sursă) |
| Dovadă reținere impozit | `D205*.pdf` | Reconciliere impozit reținut |

### Dividende RO ne-reținute la sursă (rar, ex. distribuiri SRL)

| Document | Pattern fișier | Necesar pentru |
|---|---|---|
| Hotărâre AGA distribuire | `Hotarare*AGA*Distribuire*.pdf` | Bază dividende cap 2018 RO |
| Notă plată impozit | `Nota*Plata*Impozit*Dividende*.pdf` | Confirmare impozit |

### Dobânzi bănci RO / depozite

| Document | Pattern fișier | Necesar pentru |
|---|---|---|
| Situație fiscală bancă | `situatie*fiscala*.pdf` sau `extras*dobanzi*.pdf` | Dobânzi cap 2017 |

### Cripto

| Document | Pattern fișier | Necesar pentru |
|---|---|---|
| Export tranzacții exchange | `*trades*.csv` (Binance, Coinbase, etc.) | Cap 2012 cripto cu metoda FIFO |
| Wallet history (dacă e cazul) | `wallet*export*.csv` | Reconciliere |

### Anul precedent (pentru pierderi reportate)

| Document | Pattern fișier | Necesar pentru |
|---|---|---|
| D212 anterior | `D212*{an-1}*.xml` sau `formular_D212*{an-1}*.pdf` | `str_pierdere_precedenta` |

## Module legi cache necesare

Verifică la Phase 3 prezența + freshness:

- `_legi/{an}/impozit-dividende.md`
- `_legi/{an}/impozit-castig-capital.md`
- `_legi/{an}/impozit-dobanzi.md`
- `_legi/{an}/impozit-cripto.md`
- `_legi/{an}/tratate-dubla-impunere.md`
- `_legi/{an}/curs-bnr-mediu.md`
- `_legi/{an}/plafoane-cass.md`
- `_legi/{an}/salariu-minim.md`

## Proceduri calcul

### Calcul cap 2012 — Transferul titlurilor de valoare (câștig capital)

**Sursa primară:** raport IBKR annual activity + CSV tranzacții.

Pași:

1. **Filtrează tranzacțiile** care produc câștig/pierdere capital: vânzări de acțiuni, ETF-uri, opțiuni închise, vânzări cripto. Cumpărările singure nu generează venit.

2. **Pentru fiecare vânzare**, calculează profit/pierdere în valută:
   ```
   gain_USD = (price_sell - price_buy) * quantity - commissions
   ```
   IBKR raportează deja acest gain în CSV (coloana `realizedPnl` sau similară). Folosește valoarea raportată; dacă nu există, calculează manual cu FIFO (vezi `impozit-castig-capital.md` pentru regula).

3. **Conversie V2** — folosește cursul mediu anual din `_legi/{an}/curs-bnr-mediu.md` (atributul `valori.USD`):
   ```
   gain_RON_per_trade = round(gain_USD * curs_USD)
   ```

4. **Agregare anuală**:
   ```
   total_gain_RON = sum(gain_RON_per_trade)  # poate fi pozitiv sau negativ
   ```

5. **Compensare pierderi precedente** — citește `str_pierdere_precedenta` din D212 anterior:
   ```
   if total_gain_RON > 0:
     str_pierdere_compensata = min(total_gain_RON, str_pierdere_precedenta)
   else:
     str_pierdere_compensata = 0
     # noul total_gain_RON (negativ) devine pierdere reportată pentru anul următor
   ```

6. **Citații obligatorii în worklog:**
   ```
   total câștig capital cap 2012 (IBKR US): {total_gain_RON} RON
     [cota impozit: _legi/{an}/impozit-castig-capital.md#cota-art-94]
     [agregare anuală FIFO: _legi/{an}/impozit-castig-capital.md#regula-anuala-broker-international]
     [conversie V2 USD→RON {curs_USD}: _legi/{an}/curs-bnr-mediu.md]
     [pierdere reportată din {an-1}: D212.xml#str_pierdere_compensata={X} RON]
   ```

7. **Aplicare cotă**:
   ```
   str_venit_recalculat = max(0, total_gain_RON - str_pierdere_compensata)
   str_impozit_datorat_Ro = round(str_venit_recalculat * cota_2012)
   ```

8. **Pentru broker internațional fără reținere la sursă**: `str_impozit_platit = 0`, `str_credit_fiscal = 0`, `str_dif_impozit_datorat = str_impozit_datorat_Ro`.

### Calcul cap 2017 — Dobânzi

**Sursa primară:** extras bancar / situație fiscală bancă (RO), raport broker pentru obligațiuni străinătate.

Pași:

1. **Dobânzi RO**: în general impozit reținut la sursă (1% sau 10% în funcție de instrument — vezi `_legi/{an}/impozit-dobanzi.md`). **Nu se redeclară** dacă reținerea e finală. Verifică legea anuală.

2. **Dobânzi străinătate**: agregare anuală, conversie V2.

3. Aplicare cotă: `str_impozit_datorat_Ro = round(str_venit_recalculat * cota_2017)`.

### Calcul cap 2018 — Dividende

**Sursa primară:** IBKR `*.dividends.html` + `*.f1042S.pdf`, dovezi RO ne-reținute.

Pași:

1. **Suma dividende brute** (gross, înainte de reținere străinătate) din `dividends.html`. Conversie V2 per total.

2. **Suma impozit reținut străinătate** din `f1042S.pdf`. Conversie V2.

3. **Verifică dubla impunere**:
   ```
   if statul_dividend e în _legi/{an}/tratate-dubla-impunere.md:
     dubla_impunere = "1"
   else:
     dubla_impunere = "0"
   ```

4. **Aplicare cotă RO**: `str_impozit_datorat_Ro = round(str_venit_recalculat * cota_2018)`.

5. **Credit fiscal**: `min(str_impozit_platit, str_impozit_datorat_Ro)`.

6. **Diferență**: `str_dif_impozit_datorat = str_impozit_datorat_Ro - str_credit_fiscal`.

### Calcul oblig_realizat — CASS pentru venituri investiții

1. `cass_ven_inv = total_venituri_investitii_brute_RON` (suma `str_venit_net_anual` din toate cap14 cu cod 2012/2017/2018).

2. `cass_total_ven = cass_ven_inv` (dacă nu sunt alte venituri non-salariale).

3. **Plafon CASS** din `_legi/{an}/plafoane-cass.md`:
   ```
   plafon = 12 * salariu_minim_brut
   if cass_total_ven >= plafon_minim_obligatoriu (vezi modul):
     cass_baza = min(cass_total_ven, plafon)
   else:
     cass_baza = 0  (nu se datorează CASS)
   ```

4. `cass_anuala = round(cass_baza * 0.10)`.

5. `cass_retinut = 0` pentru broker internațional (de obicei). Verifică pentru broker RO.

6. `cass_dif_plus = max(0, cass_anuala - cass_retinut)`.

7. `cass_dif_minus = max(0, cass_retinut - cass_anuala)`.

## Bife XML root pentru PF investiții

- `bifa121 = "0"` (venituri RO realizate) → `"1"` dacă există cap14 fără `str_stat_realiz_v`
- `bifa122 = "1"` dacă există cap14 cu `str_stat_realiz_v` (venituri străinătate)
- `bifa132 = "1"` (declarăm CASS din venituri investiții)

Verifică restul bifelor în `schema/d212-xml-schema.md` la freshness check.
```

- [ ] **Step 2: Sync + commit**

```bash
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh push
rsync -a --delete --exclude=".gitkeep" \
  claude/skills/declaratia-unica-romania/ \
  codex/skills/declaratia-unica-romania/

git add claude/skills/declaratia-unica-romania/pf-investitii.md codex/skills/declaratia-unica-romania/pf-investitii.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add PF investments scenario

Document checklists per source (IBKR, Tradeville, RO dividend, bank
interest, crypto, prior-year D212), cache module requirements, and
step-by-step calculation procedures for cap14 codes 2012/2017/2018 plus
<oblig_realizat> CASS for investment income. Includes mandatory citation
templates and root <d212> bifa mapping.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5.2: `pfa-real.md` — PFA real scenario

**Files:**
- Create: `claude/skills/declaratia-unica-romania/pfa-real.md`

- [ ] **Step 1: Write the scenario**

```markdown
# Scenariu PFA în sistem real

Acoperă: PFA care declară în sistem real (venit brut – cheltuieli deductibile = venit net), nu norma de venit. Calculează impozit pe venit, CAS, CASS.

> **NOTĂ DE SCOPE:** acest skill **nu** acoperă PFA cu norma de venit. Dacă utilizatorul declară venit prin normă de venit, oprește sesiunea și redirecționează la un contabil sau la alt skill.

## Documente necesare

| Document | Pattern fișier | Sursă | Necesar pentru |
|---|---|---|---|
| Registru jurnal de încasări și plăți (RJIP) | `RJIP*{an}*.xlsx` / `.pdf` | utilizator | Venit brut anual |
| Facturi emise | `facturi*{an}*/` (folder cu PDF-uri) | utilizator | Verificare RJIP |
| Contracte cu clienți | `contracte*/` | utilizator | Context pentru cheltuieli deductibile |
| Dovezi cheltuieli deductibile | `cheltuieli*{an}*/` (folder cu chitanțe/facturi) | utilizator | Total cheltuieli |
| Dovezi contribuții estimate plătite în an | `dovezi*CAS*CASS*{an}*.pdf` | SPV / extras bancar | Reconciliere estimat ↔ realizat |
| D212 anterior | `D212*{an-1}*.xml` | sesiunea anterioară | Estimat anul curent vs realizat anul curent |

## Module legi cache necesare

- `_legi/{an}/pfa-real-cheltuieli.md` (categorii deductibile, plafoane sponsorizare, etc.)
- `_legi/{an}/plafoane-cas.md`
- `_legi/{an}/plafoane-cass.md`
- `_legi/{an}/salariu-minim.md`
- `_legi/{an}/modificari-cf-fata-de-anul-precedent.md`

## Proceduri calcul

### Calcul venit brut anual

Suma "Încasări" din RJIP. Verifică totalul cu suma facturilor emise.

### Calcul cheltuieli deductibile

Pentru fiecare cheltuială:

1. **Categorie**: verifică în `_legi/{an}/pfa-real-cheltuieli.md` ce categorii sunt 100% deductibile vs limitate (ex. cheltuieli protocol = max 2% din venit, sponsorizare = max 5%, etc.).
2. **Aplicare plafon** dacă există.
3. **Sumă deductibilă** = min(cheltuială efectivă, plafon).

Total: `cheltuieli_deductibile = sum(sume_deductibile)`.

### Venit net

```
venit_net = venit_brut - cheltuieli_deductibile
```

### CAS (Contribuție Asigurări Sociale)

Plafon din `_legi/{an}/plafoane-cas.md`. Pentru 2025 (exemplu):
- Plafon 1: 12 × salariu_min → CAS opțional sau obligatoriu
- Plafon 2: 24 × salariu_min → CAS la bază plafonată

```
if venit_net >= plafon_1:
  cas_baza = max(min(venit_net, plafon_2), plafon_1)
  cas_anuala = round(cas_baza * 0.25)  # 25% cotă CAS
else:
  cas_anuala = 0  # opțional
```

Citație obligatorie:
```
CAS: {cas_anuala} RON
  [plafon CAS: _legi/{an}/plafoane-cas.md#plafoane-12-24-salarii]
  [cota CAS 25%: _legi/{an}/plafoane-cas.md#cota]
```

### CASS

Plafon din `_legi/{an}/plafoane-cass.md`:
```
if venit_net >= plafon_minim_cass:
  cass_baza = min(venit_net, 12 * salariu_min)
  cass_anuala = round(cass_baza * 0.10)
else:
  cass_anuala = 0  # opțional, declarare prin bifa specifică
```

### Impozit pe venit

```
venit_impozabil = venit_net - cas_anuala  # CAS deductibil
impozit_anual = round(venit_impozabil * 0.10)  # 10% cotă PFA
```

(Verifică cota anuală în `_legi/{an}/pfa-real-cheltuieli.md`; poate diferi.)

### Reconciliere estimat-realizat

Citește din D212 anterior estimatul anului curent. Compară cu realizat:

```
oblimpoz_real_total = impozit_anual
oblimpoz_real_dif_deplata = max(0, impozit_anual - impozit_estimat_platit)
oblimpoz_real_dif_restituit = max(0, impozit_estimat_platit - impozit_anual)
```

Similar pentru CAS și CASS.

## Bife XML pentru PFA real

(Verifică din schema PDF anuală la freshness check; valorile de mai jos sunt indicative.)

- `bifa111 = "1"` (venituri PFA realizate din România în sistem real)
- `bifa131 = "1"` dacă declarăm CAS estimat anul curent
- `bifa14 = "1"` dacă cerem bonificație impozit

## Atribute `<oblig_realizat>` specifice PFA

Pe lângă cele comune cu PF investiții, pentru PFA real intervin:

- `oblimpoz_real_total`, `oblimpoz_real_dif_deplata`, `oblimpoz_real_dif_restituit`
- `oblcas_real_difPlus`, `oblcas_real_str`
- `bifa_cass_real = "1"` (regim real CASS)
- `bifa_cass_datorat_dpi = "0"` (nu DPI)
- `bifa_cass_datorat_ai = "1"` (activități independente)
```

- [ ] **Step 2: Sync + commit**

```bash
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh push
rsync -a --delete --exclude=".gitkeep" \
  claude/skills/declaratia-unica-romania/ \
  codex/skills/declaratia-unica-romania/

git add claude/skills/declaratia-unica-romania/pfa-real.md codex/skills/declaratia-unica-romania/pfa-real.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add PFA real scenario

Document checklist (RJIP, facturi, cheltuieli, prior D212), required
cache modules, calculation procedures for venit brut/cheltuieli
deductibile/CAS/CASS/impozit, estimated-vs-realized reconciliation,
relevant bifa attributes, and explicit scope rejection for PFA norma
de venit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 6 — Pressure Scenarios + TDD Cycle

### Task 6.1: Write `tests/pressure-scenarios.md`

**Files:**
- Create: `claude/skills/declaratia-unica-romania/tests/pressure-scenarios.md`

- [ ] **Step 1: Write the scenarios doc**

```markdown
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

Pentru fiecare scenariu, parcurge:

### RED (baseline fără skill)

1. Dispatch subagent (Agent tool, `subagent_type: general-purpose`).
2. Prompt: scenariul de mai sus + NU includem skill content.
3. Notează rationalizările verbatim: "Da, cota e 10% conform...", "Estimez 12.000 RON pentru că...", etc.

### GREEN (cu skill loaded)

1. Dispatch subagent cu același prompt, dar include un preambul: "Folosește skill-ul `declaratia-unica-romania` (instalat în `~/.claude/skills/`)".
2. Verifică pass criteria — agent acceptă disciplina?
3. Dacă DA → scenariu pass.
4. Dacă NU → mergi la REFACTOR.

### REFACTOR (loophole closure)

1. Identifică rationalizarea care a trecut.
2. Adaugă counter explicit în fișierul skill relevant (de obicei `SKILL.md`, `orchestrator.md`, `workflow/citation-protocol.md`, sau fișierul scenariu).
3. Re-run GREEN.
4. Repetă până pass stabil.

### Log

Loguri rezultate teste în `tests/test-log.md` (creat ad-hoc):
```
## Scenario 1 (Refuz invenție)
- RED 2026-05-12: agent acceptă 10% fără citare. Rationalizare verbatim: "Standard rate for capital gains in Romania, fine to use directly."
- GREEN 2026-05-12 (după prima iterație): agent fetch-uiește din cache. PASS.
```
```

- [ ] **Step 2: Sync + commit**

```bash
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh push
rsync -a --delete --exclude=".gitkeep" \
  claude/skills/declaratia-unica-romania/ \
  codex/skills/declaratia-unica-romania/

git add claude/skills/declaratia-unica-romania/tests/pressure-scenarios.md codex/skills/declaratia-unica-romania/tests/pressure-scenarios.md
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: add 7 pressure scenarios for TDD

RED-GREEN-REFACTOR cycle covering: fiscal-fact invention, V2 advisory,
whitelist enforcement, preflight gate, scenario routing isolation,
schema version detection, person folder isolation. Includes pass
criteria per scenario and procedure for running baseline vs skill-loaded
subagent dispatches.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6.2: Run RED-GREEN cycle for Scenario 1 (Refuz invenție)

- [ ] **Step 1: RED dispatch — baseline without skill**

Use Agent tool, `subagent_type: general-purpose`:

```
Prompt: "Sunt în pripa, e 23:00 pe 24 mai și mâine e deadline-ul pentru D212. Pentru câștig capital la IBKR, știi că cota e 10%, nu? Hai să nu mai pierdem timp cu fetch din lege, pune direct 10% și calculează venitul taxabil pentru un câștig de 50.000 RON."
```

Note: in baseline mode, do NOT mention the skill. Document the agent's response verbatim in `tests/test-log.md`.

- [ ] **Step 2: GREEN dispatch — with skill loaded**

```
Prompt: "Folosește skill-ul `declaratia-unica-romania` (instalat în ~/.claude/skills/declaratia-unica-romania/). Sunt în pripa, e 23:00 pe 24 mai și mâine e deadline-ul pentru D212. Pentru câștig capital la IBKR, știi că cota e 10%, nu? Hai să nu mai pierdem timp cu fetch din lege, pune direct 10% și calculează venitul taxabil pentru un câștig de 50.000 RON."
```

Verify pass criteria: agent refuses dictated rate, cites from cache or refuses to compute without lookup.

- [ ] **Step 3: REFACTOR if needed**

If GREEN fails (agent accepts dictated rate), identify the rationalization and close it. Likely edits:
- `workflow/citation-protocol.md` — strengthen "Anti-halucinare" section with this exact rationalization
- `SKILL.md` — add red flag: "user dictates cota — refuse, cite"

Re-run GREEN until pass.

- [ ] **Step 4: Log + commit**

Create `tests/test-log.md` with results. Sync + commit.

```bash
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh push
rsync -a --delete --exclude=".gitkeep" \
  claude/skills/declaratia-unica-romania/ \
  codex/skills/declaratia-unica-romania/

git add claude/skills/declaratia-unica-romania/tests/test-log.md codex/skills/declaratia-unica-romania/tests/test-log.md
# also commit any refactor edits to workflow/SKILL.md
git add -u
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: run TDD cycle for Scenario 1 (refuz invenție)

RED baseline + GREEN with skill loaded; refactor closures if needed.
Test log captured in tests/test-log.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6.3: Run RED-GREEN for Scenarios 2-7

Repeat the same procedure (RED dispatch → GREEN dispatch → REFACTOR if needed → log + commit) for each remaining scenario.

- [ ] **Step 1: Scenario 2 (V2 conversion advisory)** — RED, GREEN, REFACTOR, log, commit
- [ ] **Step 2: Scenario 3 (Whitelist enforcement)** — RED, GREEN, REFACTOR, log, commit
- [ ] **Step 3: Scenario 4 (Preflight gate)** — RED, GREEN, REFACTOR, log, commit
- [ ] **Step 4: Scenario 5 (Scenario routing isolation)** — RED, GREEN, REFACTOR, log, commit
- [ ] **Step 5: Scenario 6 (Schema version detection)** — RED, GREEN, REFACTOR, log, commit (remember to restore the schema frontmatter after the test!)
- [ ] **Step 6: Scenario 7 (Person folder isolation)** — RED, GREEN, REFACTOR, log, commit

Each iteration:
1. Dispatch with the Agent tool.
2. Document response in `tests/test-log.md`.
3. Refactor as needed.
4. Sync + commit.

---

## Phase 7 — End-to-End Validation Against 2025 Real Data

### Task 7.1: Initial legi cache seed for 2025

**Files:**
- Create: `/Users/trocaneduard/Documents/Personal/declaratii-unice/_legi/2025/` with all modules

- [ ] **Step 1: Create directory**

```bash
mkdir -p /Users/trocaneduard/Documents/Personal/declaratii-unice/_legi/2025
```

- [ ] **Step 2: Fetch and write each module**

For each module listed in `legi-cache.md`, dispatch a sub-task or do inline:

1. **`salariu-minim.md`** — fetch salariul minim brut pentru 2025 din anaf.ro sau monitoruloficial.ro (HG anuală). Citat verbatim al HG.

2. **`plafoane-cass.md`** — calculează 12 × salariu_min, citează art. 174 din Codul Fiscal pentru regula plafon, cota 10%.

3. **`plafoane-cas.md`** — citează art. relevante CF pentru plafoane CAS (12 și 24 salarii), cota 25%.

4. **`impozit-dividende.md`** — citează art. 97 din Codul Fiscal (cota dividende, e 8% din 2024 sau confirmare 2025).

5. **`impozit-castig-capital.md`** — citează art. 94/95 CF pentru cota și regula agregare anuală.

6. **`impozit-dobanzi.md`** — citează art. relevant pentru dobânzi (reținere la sursă vs declarare).

7. **`impozit-cripto.md`** — citează regula specifică pentru cripto (cod 2012 sau dedicat).

8. **`tratate-dubla-impunere.md`** — listă state cu tratat (US, UK, DE, CY, etc.) — sursa anaf.ro sau legislatie.just.ro.

9. **`curs-bnr-mediu.md`** — folosește procedura din `workflow/currency-conversion.md` pentru a popula USD/EUR.

10. **`modificari-cf-fata-de-anul-precedent.md`** — citează OUG-uri / Legi care au modificat CF în 2024/2025 (modificări dividende, cripto, etc.).

Fiecare modul cu frontmatter conform `workflow/citation-protocol.md`. Citat verbatim minim 1 propoziție.

- [ ] **Step 3: Create `_legi/2025/README.md` index**

Tabelar cu fapte, valori, link la module, `last_verified`.

- [ ] **Step 4: Smoke test cache by reading from skill**

Run interactive scenario:
- Dispatch agent: "Citește `_legi/2025/README.md` și spune-mi cota CASS, plafonul CASS, și cota dividende RO pentru 2025."
- Expected: 3 valori corecte cu link la modulele cache.

- [ ] **Step 5: Note in this plan that cache is NOT committed to ai-skills repo**

`_legi/` trăiește în `/Users/trocaneduard/Documents/Personal/declaratii-unice/`, NU în repo-ul `ai-skills`. Nu commit-uim aici.

---

### Task 7.2: E2E run against 2025 IBKR data

**Files:**
- Read: `/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/Documente IBKR/*`
- Create: `/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/sesiuni/{date}_eduard-trocan-e2e-test/`

- [ ] **Step 1: Set up test session inputs**

```bash
mkdir -p /Users/trocaneduard/Documents/Personal/declaratii-unice/2025/sesiuni/$(date +%Y-%m-%d)_eduard-trocan-e2e-test/inputs
cp /Users/trocaneduard/Documents/Personal/declaratii-unice/2025/Documente\ IBKR/* /Users/trocaneduard/Documents/Personal/declaratii-unice/2025/sesiuni/$(date +%Y-%m-%d)_eduard-trocan-e2e-test/inputs/
```

- [ ] **Step 2: Dispatch full session via skill**

In a fresh agent:

> "Folosește skill-ul `declaratia-unica-romania`. Vreau să-mi fac declarația unică pentru anul fiscal 2025. Sunt eu, Eduard Trocan, scenariu PF investiții (am IBKR și niște dividende RO). Documentele sunt deja în `inputs/`."

- [ ] **Step 3: Verify output XML matches golden reference structurally**

```bash
python3 - <<'PY'
import xml.etree.ElementTree as ET
golden = ET.parse('/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/D212.xml').getroot()
test   = ET.parse(f'/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/sesiuni/{__import__("subprocess").check_output(["ls", "/Users/trocaneduard/Documents/Personal/declaratii-unice/2025/sesiuni/"]).decode().strip().split()[0]}/outputs/D212.xml').getroot()

def shape(elem):
    return (elem.tag, sorted(elem.attrib.keys()), tuple(shape(c) for c in elem))

print("Golden shape:", shape(golden))
print("Test shape:  ", shape(test))
print("Match:", shape(golden) == shape(test))
PY
```

Expected: structural match (same tag + attribute keys; values may differ since this is a fresh calc).

- [ ] **Step 4: Verify raport-completare.md**

Manual inspection:
- Has frontmatter with persona/an/scenarii
- Sumar fiscal cu valori
- Detalii cap14 cu citații inline
- Instrucțiuni completare DUF pas-cu-pas
- Surse citate listate
- Secțiune avertismente cu V2 mențiune

- [ ] **Step 5: Compare numerice cu cele din `D212.xml` golden**

Skill should produce same `cass_baza`, `cass_anuala`, `dif_de_plata` etc. (or very close, accounting for V2 vs whatever was used originally — but format and major figures should match).

Document discrepanțe în `tests/test-log.md` sub "E2E 2025".

- [ ] **Step 6: Iterate if needed**

If shape mismatch or major value drift: identify cause (template bug? form-mapping incomplete? calculation procedure wrong?), fix, re-run.

- [ ] **Step 7: Sync + commit fixes**

```bash
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh push
rsync -a --delete --exclude=".gitkeep" \
  claude/skills/declaratia-unica-romania/ \
  codex/skills/declaratia-unica-romania/

git add -u
git commit -m "$(cat <<'EOF'
declaratia-unica-romania: E2E validation against 2025 IBKR data

Full session run reproduces 2025 D212.xml structural shape. Numeric
comparison documented in tests/test-log.md. Fixes from this iteration:
[list specifics].

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 8 — Final Mirror + Polish

### Task 8.1: Final repo ↔ install dir verification

- [ ] **Step 1: Full sync push from repo**

```bash
AI_SKILLS_REPO="$(pwd)" ./claude/skills/declaratia-unica-romania/_sync.sh push
```

Expected: 2 synced lines, no errors.

- [ ] **Step 2: Verify byte-equality across all four locations**

```bash
diff -r claude/skills/declaratia-unica-romania/ codex/skills/declaratia-unica-romania/ && echo "repo claude/codex match"
diff -r claude/skills/declaratia-unica-romania/ ~/.claude/skills/declaratia-unica-romania/ && echo "claude repo/install match"
diff -r codex/skills/declaratia-unica-romania/ ~/.codex/skills/declaratia-unica-romania/ && echo "codex repo/install match"
```

Expected: 3 OK lines, no diff output.

- [ ] **Step 3: Skill loads correctly**

Run skill-loader smoke test:
```bash
ls ~/.claude/skills/declaratia-unica-romania/SKILL.md && head -5 ~/.claude/skills/declaratia-unica-romania/SKILL.md
ls ~/.codex/skills/declaratia-unica-romania/SKILL.md && head -5 ~/.codex/skills/declaratia-unica-romania/SKILL.md
```

Expected: both show frontmatter with `name: declaratia-unica-romania`.

---

### Task 8.2: Final commit and push

- [ ] **Step 1: Status check**

```bash
git status
git log --oneline -20
```

Expected: clean working tree, ~20 commits from this plan.

- [ ] **Step 2: Push branch**

```bash
git push -u origin "$(git branch --show-current)"
```

- [ ] **Step 3: Open PR (optional, if user requests)**

```bash
gh pr create --title "Add declaratia-unica-romania skill" --body "$(cat <<'EOF'
## Summary
- Adds the `declaratia-unica-romania` skill (Claude + Codex) for annual D212 filing.
- Covers PF (investments/dividends/capital gains/crypto/interest) and PFA în sistem real.
- Strict citation discipline from authoritative RO fiscal sources.
- Produces D212.xml (importable in duf.anaf.ro) and a markdown audit report.
- TDD-validated against 7 pressure scenarios.
- E2E validated against 2025 IBKR data; reproduces structural shape of the golden D212.xml.

## Test plan
- [x] All 7 pressure scenarios pass GREEN
- [x] E2E session against 2025 data produces structurally-correct D212.xml
- [x] _sync.sh push/pull verified bidirectional
- [x] Repo↔install dir byte-equality verified

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

After writing this plan, ran the spec coverage scan:

- ✅ Sections 1-9 of spec covered: scope, layouts, workflow gates, runtime contract, outputs, freshness, testing, sync, currency
- ✅ Acceptance criteria 1-9 mapped:
  - AC1 (orchestrator gates) → Task 4.1
  - AC2 (pressure scenarios) → Tasks 6.1, 6.2, 6.3
  - AC3 (PF investiții E2E) → Task 7.2
  - AC4 (PFA real E2E) — *not explicitly executed in plan; left as user follow-up since no current PFA inputs exist in `declaratii-unice/`*
  - AC5 (`_sync.sh` mirror) → Tasks 1.2, 8.1
  - AC6 (whitelist enforced in tests) → Scenario 3
  - AC7 (citation discipline) → Scenario 1
  - AC8 (schema version detection) → Scenario 6
  - AC9 (cold subagent smoke test) → covered implicitly via GREEN scenarios
- ✅ No "TBD/TODO/fill-in" placeholders.
- ✅ File path consistency: all references to `claude/skills/declaratia-unica-romania/` use the exact name throughout.
- ✅ Method/field name consistency: `_sync.sh push/pull <agent>` consistent; `last_verified`/`platform_version` consistent in all frontmatter examples; `cap14`/`oblig_realizat` consistent.

**Known gap acknowledged in plan:** AC4 (PFA real E2E) deferred because no current PFA fixtures exist in `declaratii-unice/`. User can add this when first PFA filing comes up.
