# Template `raport-completare.md`

Acest fișier definește structura **obligatorie** a raportului produs în Faza 6. Agentul completează cu valori reale; nu inventează câmpuri suplimentare și nu omite secțiuni.

Secțiunea critică e **§4 "Instrucțiuni completare manuală în DUF"** — utilizatorul trebuie să poată parcurge raportul în browser deschis pe `duf.anaf.ro` și să completeze pas cu pas, câmp cu câmp.

---

## Structura completă

```markdown
---
persoana: <nume complet>
cnp: <13 cifre>
an_fiscal: <YYYY>
scenarii: <PF investiții | PFA real | combinat>
agent: <claude | codex>
data_generare: <YYYY-MM-DD HH:MM>
conversie_valutara: V2 — media anuală cursbnr.ro (cross-check BNR 3 puncte)
duf_platform_version: <V-x.y.z>
---

# Raport completare D212 — anul fiscal {an_fiscal}

## 1. Sumar fiscal

| Indicator | Valoare (RON) |
|---|---|
| Impozit pe venit total | {oblimpoz_real_total} |
| CAS | {cas_plus} |
| CASS | {cass_anuala} |
| Diferență de plată | **{dif_de_plata}** |
| Diferență de restituit | {dif_de_restituit} |
| Cont bancar pentru restituiri | {iban} |

## 2. Detalii per linie de venit

[Pentru fiecare cap14, secțiune separată cu raw / conversie / citații / calculat.]

### 2.1 — {descriere scurtă, ex. "Câștig capital IBKR (US, cod 2012)"}

**Sursa raw:** `inputs/<fișier>.pdf` / `inputs/<fișier>.csv`

| Câmp | Valoare raw | Conversie | Valoare RON |
|---|---|---|---|
| Venit brut | {USD} USD | × {curs_USD} (cursbnr.ro 2025) | {RON} |
| Impozit reținut străinătate | {USD} USD | × {curs_USD} | {RON} |

**Citații lege:**
- [cota impozit: `_legi/{an}/impozit-castig-capital.md#cota-art-94`]
- [regula agregare: `_legi/{an}/impozit-castig-capital.md#regula-anuala-broker-international`]

**Calcul:**
```
str_venit_net_anual = 149.655 RON
str_pierdere_precedenta = 21.812 RON (din D212 anul trecut)
str_pierdere_compensata = 21.812 RON
str_venit_recalculat = 127.843 RON
str_impozit_datorat_Ro = 127.843 × 10% = 12.784 RON
str_credit_fiscal = 0 RON (broker US nu reține pe câștig capital)
str_dif_impozit_datorat = 12.784 RON
```

[Repeta pentru fiecare linie cap14.]

## 3. Calcul `<oblig_realizat>` — CASS și total

[Doar dacă CASS e datorat. Altfel, secțiune scurtă: "CASS nu se datorează în acest an fiscal; baza calc sub plafon minim. Vezi `_legi/{an}/plafoane-cass.md#prag-minim`."]

```
cass_total_ven = {suma venituri investiții brute} RON
plafon = 12 × salariu_minim = {valoare} RON  [_legi/{an}/plafoane-cass.md]
cass_baza = min(cass_total_ven, plafon) = {valoare} RON
cass_anuala = cass_baza × 10% = {valoare} RON
cass_retinut = {valoare} RON
cass_dif_plus = max(0, cass_anuala - cass_retinut) = {valoare} RON
```

## 4. Instrucțiuni completare manuală în DUF

Deschide `https://www.anaf.ro/declaratii/duf` într-un browser nou. **Mediu: Public** — nu necesită autentificare pentru completare și export XML.

> **Notă:** dacă preferi import automat în loc de completare manuală, sari direct la §6 "Pași finali" — XML-ul `outputs/D212.xml` poate fi importat în DUF cu un click. Această secțiune e pentru completare manuală câmp-cu-câmp (sau ca dublu-check după import).

### Pasul 1 — Date de identificare

Click pe tab-ul **"Date de identificare"** (prima secțiune).

| Câmp DUF | Valoare de completat |
|---|---|
| Nume | {nume} |
| Inițiala tatălui | {initiala_tata} |
| Prenume | {prenume} |
| CNP | {cnp} |
| Cont bancar (IBAN) | {iban} |
| Telefon | {telefon} |
| Email | {email} |
| Nerezident | lăsa **neselectat** (rezident) |

Treci la secțiunea următoare.

### Pasul 2 — Venituri realizate

Click pe tab-ul **"Venituri realizate"**.

[Pentru fiecare cap14, generează un sub-pas separat: 2.a, 2.b, 2.c, ...]

#### 2.a — {descriere, ex. "Câștig capital IBKR (US, cod 2012)"}

Click pe butonul **"Adaugă venit străinătate"** (sau **"Adaugă venit România"** pentru cap14 fără țară).

În formularul care apare, completează:

| Câmp DUF | Valoare |
|---|---|
| Țară | {den_stat} (selectează din dropdown) |
| Categorie venit | {cod_categorie} — {denumire_categorie} (selectează din dropdown) |
| Bifă "Dublă impunere" | {DA dacă dubla_impunere=1, altfel NU} |
| Venit net anual (RON) | **{str_venit_net_anual}** |
| Pierdere precedentă reportată (RON) | {str_pierdere_precedenta sau "—" dacă absent} |
| Pierdere compensată în anul curent (RON) | {str_pierdere_compensata} |
| Venit recalculat (RON) | _auto-calculat de DUF: {str_venit_recalculat}_ |
| Impozit datorat în RO (RON) | _auto-calculat de DUF: {str_impozit_datorat_Ro}_ |
| Impozit plătit în străinătate (RON) | {str_impozit_platit} |
| Credit fiscal (RON) | _auto-calculat de DUF: {str_credit_fiscal}_ |
| Diferență impozit datorat (RON) | _auto-calculat de DUF: {str_dif_impozit_datorat}_ |

Click **"Salvează"** sau **"Continuă"** pentru a închide formularul.

[Repeta 2.b, 2.c, etc. pentru fiecare cap14.]

### Pasul 3 — Date privind CASS

[Dacă CASS = 0:]
**Sari acest pas.** CASS nu e datorat (baza sub plafon minim). DUF va completa automat secțiunea cu valori zero la export.

[Dacă CASS > 0:]
Click pe tab-ul **"Date privind CASS"**.

| Câmp DUF | Valoare |
|---|---|
| Regim CASS | Regim real (bifa_cass_real = 1) |
| Tip venit | Venituri din investiții (bifa_cass_datorat_ai = 1) |
| Venituri totale (RON) | {cass_total_ven} |
| Bază CASS (RON) | {cass_baza} (plafonat la 12 × salariu minim) |
| Cotă | 10% (constant) |
| CASS anuală (RON) | **{cass_anuala}** |
| CASS reținut la sursă (RON) | {cass_retinut} |
| Diferență CASS de plată (RON) | _auto-calculat: {cass_dif_plus}_ |

### Pasul 4 — Date privind CAS

[Pentru PFA real cu venit ≥ plafon CAS — vezi `pfa-real.md` pentru calcul. Pentru PF investiții, sari pasul.]

### Pasul 5 — Sumar fiscal (verificare)

DUF afișează în partea de jos a paginii sumarul calculat:

| Indicator | Skill | DUF (după completare) |
|---|---|---|
| Impozit pe venit total | {oblimpoz_real_total} | _verifică să match-uiască_ |
| CASS total | {cass_anuala} | _verifică_ |
| Diferență de plată | **{dif_de_plata}** | _verifică_ |

**Dacă DUF afișează valori diferite:** stop. Re-verifică inputs și calcule. Skill-ul a greșit ceva.

## 5. Surse citate

[Listă cu URL + accessed_on + source_type pentru fiecare fapt fiscal folosit. Generat automat din frontmatter-ele modulelor cache `_legi/{an}/`.]

| Fapt | Sursă | Accessed | Tip |
|---|---|---|---|
| Cota impozit câștig capital 10% | https://legislatie.just.ro/... | 2026-05-12 | pagina-oficiala |
| Plafon CASS 12×salariu_min | https://anaf.ro/... | 2026-05-12 | pdf-oficial |
| Curs mediu USD 2025 | https://www.cursbnr.ro/curs-valutar-mediu | 2026-05-12 | pagina-convenience (cross-check BNR) |
| ... | | | |

## 6. Pași finali (după completare în DUF)

1. **DUF round-trip — formă canonică:**
   - Click **"Descarcă XML"** în DUF după salvarea tuturor secțiunilor.
   - Salvează ca `outputs/D212.canonical.xml` (NU înlocui `D212.xml`).
   - Vezi `workflow/duf-roundtrip.md` pentru detalii și diff de atribute față de XML-ul brut.

2. **Submit electronic prin SPV:**
   - Login la `https://www.anaf.ro/spv/` cu certificat digital sau credențiale ANAF.
   - Upload `D212.canonical.xml`.
   - Confirmă submit.

3. **Plată diferență:**
   - {dif_de_plata} RON la cont ANAF — vezi cont destinație în Instrucțiunile anuale ANAF (`_legi/{an}/`).
   - Termen: 25 mai {an_fiscal+1}.

## 7. Avertismente

- **Conversie V2:** Acest raport folosește media anuală cursbnr.ro pentru conversia USD/EUR → RON, nu cursul BNR per tranzacție prevăzut de art. 76 alin. (2) din Codul Fiscal. Vezi `workflow/currency-conversion.md` și `_legi/{an}/curs-bnr-mediu.md` pentru cross-check BNR și implicații la control fiscal.

- **Bifele root XML:** valorile finale (`bifa121`, `bifa122`, `bifa132`) sunt setate de DUF la re-export, nu de skill. Vezi `workflow/duf-roundtrip.md`.

- **`totalPlata_A`:** checksum CNP, nu total fiscal. Nu te alarma că nu corespunde sumei de plată.

- [Alte avertismente specifice sesiunii, ex. "Pierderi reportate din 2024 verificate manual contra D212.xml anterior."]
```

---

## Reguli de generare

1. **Toate variabilele `{...}`** se substituie cu valori reale calculate la Faza 5. Nu lăsa placeholderi în raportul final.

2. **§4 (instrucțiuni manuale) este obligatorie.** Generează un sub-pas (2.a, 2.b, ...) pentru fiecare `<cap14>` din XML, în aceeași ordine ca în XML. Folosește tabel cu coloane `Câmp DUF` | `Valoare`. Marchează câmpurile auto-calculate de DUF cu italic + textul `_auto-calculat de DUF: {valoare}_`.

3. **§3 (CASS) și §4 Pasul 3 (CASS):** dacă CASS = 0, scurtează la o singură propoziție explicând că secțiunea e goală. Nu afișa tabele cu zero peste tot.

4. **§5 (Surse citate):** generează automat din frontmatter-ele `_legi/{an}/*.md` folosite efectiv în calcul. Fiecare fapt are exact o linie în tabel.

5. **§7 (Avertismente):** include cele 3 avertismente standard (V2, bife, totalPlata_A) plus orice altele specifice sesiunii (waivere preflight, asumări de date, etc.).

6. **Limba:** română peste tot. Numele coduri de categorie și atributelor XML rămân ca în sursa oficială (ex. `str_categ_venit`, `2012`, `str_dif_impozit_datorat`).

7. **Tonul:** instructional și concret. Utilizatorul deschide raportul lângă browser și-l urmărește linie cu linie. Nu prosă lungă, ci tabele și liste.

8. **Verificare la sfârșit:** validare manuală sumar fiscal skill vs DUF (Pasul 5). Dacă diverg, raportul e greșit — re-calculează.
