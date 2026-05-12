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
