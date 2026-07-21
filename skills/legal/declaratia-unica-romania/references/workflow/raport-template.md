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
categorii_pf: <dividende | titluri/instrumente financiare | dobânzi | cripto; listă>
agent: <claude | codex>
data_generare: <YYYY-MM-DD HH:MM>
conversie_valutara_metoda: <metoda susținută oficial>
conversie_valutara_ref: <_legi/{an}/conversie-valutara.md#ancora>
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
| Venit brut | {valoare} {moneda} | {metoda; curs(uri) oficial(e); dată/an; referință oficială} | {RON} |
| Impozit reținut străinătate | {valoare} {moneda} | {metoda; curs(uri) oficial(e); dată/an; referință oficială} | {RON} |

**Citații lege:**
- [cota impozit: `_legi/{an}/impozit-castig-capital.md#cota-art-94`]
- [regula agregare: `_legi/{an}/impozit-castig-capital.md#regula-anuala-broker-international`]

**Calcul:**
```
str_venit_net_anual = {valoare verificată} RON
str_pierdere_precedenta = {valoare din D212 anterior} RON
str_pierdere_compensata = {valoare calculată conform regulii verificate} RON
str_venit_recalculat = {valoare calculată} RON
str_impozit_datorat_Ro = {bază} × {cotă verificată} = {valoare} RON
str_credit_fiscal = {valoare susținută de documente și tratat} RON
str_dif_impozit_datorat = {valoare calculată} RON
```

[Repeta pentru fiecare linie cap14.]

## 3. Calcul `<oblig_realizat>` — CASS și total

[Doar dacă CASS e datorat. Altfel, secțiune scurtă: "CASS nu se datorează în acest an fiscal; baza calc sub plafon minim. Vezi `_legi/{an}/plafoane-cass.md#prag-minim`."]

```
cass_total_ven = {suma venituri investiții brute} RON
plafon = {formula oficială verificată} = {valoare} RON  [_legi/{an}/plafoane-cass.md]
cass_baza = min(cass_total_ven, plafon) = {valoare} RON
cass_anuala = cass_baza × {cotă CASS verificată} = {valoare} RON
cass_retinut = {valoare} RON
cass_dif_plus = max(0, cass_anuala - cass_retinut) = {valoare} RON
```

## 4. Instrucțiuni completare manuală în DUF

Deschide `https://www.anaf.ro/declaratii/duf` într-un browser nou. **Mediu: Public** — nu necesită autentificare pentru completare și export XML.

> **Notă:** dacă preferi importul în loc de completarea manuală, sari direct la §6 "Pași finali" și selectează candidatul `outputs/D212.xml` în DUF. Numai DUF poate confirma importul. Această secțiune este pentru completare manuală câmp-cu-câmp sau pentru verificarea datelor după import.

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
| Bază CASS (RON) | {cass_baza} ({formula plafonului verificată pentru an}) |
| Cotă | {cota CASS verificată pentru an} |
| CASS anuală (RON) | **{cass_anuala}** |
| CASS reținut la sursă (RON) | {cass_retinut} |
| Diferență CASS de plată (RON) | _auto-calculat: {cass_dif_plus}_ |

### Pasul 4 — Date privind CAS

Pentru domeniul PF investiții acoperit de acest skill, sari acest pas. Dacă datele indică o obligație dintr-un domeniu exclus, oprește și cere asistență fiscală adecvată.

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
| Cota impozit câștig capital {valoare} | {URL oficial} | {YYYY-MM-DD} | {tip sursă oficială} |
| Plafon CASS {formula și valoare} | {URL oficial} | {YYYY-MM-DD} | {tip sursă oficială} |
| Regula de conversie {categorie, an} | {URL oficial ANAF/legislatie.just.ro} | {YYYY-MM-DD} | {instrucțiune sau normă oficială} |
| Curs {monedă, dată/an} | {URL oficial al autorității cerute; BNR pentru cursurile BNR} | {YYYY-MM-DD} | publicație oficială |
| ... | | | |

## 6. Pași finali (după completare în DUF)

1. **DUF round-trip — formă canonică:**
   - Click **"Descarcă XML"** în DUF după salvarea tuturor secțiunilor.
   - Salvează ca `outputs/D212.canonical.xml` (NU înlocui `D212.xml`).
   - Vezi `references/workflow/duf-roundtrip.md` pentru detalii și diff de atribute față de XML-ul brut.
   - Dacă DUF este indisponibil, consemnează blocajul și nu continua la depunerea electronică.

2. **Submit electronic prin SPV:**
   - Login la `https://www.anaf.ro/spv/` cu certificat digital sau credențiale ANAF.
   - Upload numai `D212.canonical.xml`; `D212.xml` este candidat de import, nu fișier sigur pentru submit.
   - Confirmă submit.

3. **Plată diferență:**
   - {dif_de_plata} RON la cont ANAF — vezi cont destinație în Instrucțiunile anuale ANAF (`_legi/{an}/`).
   - Termen: {termen verificat pentru anul fiscal, cu referință oficială}.

## 7. Avertismente

- **Conversie valutară:** metoda fiscală folosită este `{metoda}`, susținută de `{sursa oficială și ancora}` pentru `{categorie}` și `{an}`; fiecare curs provine din `{autoritatea oficială și URL}`, inclusiv direct din BNR pentru cursurile BNR. Orice calcul alternativ este etichetat separat drept comparație și nu alimentează valorile D212.

- **Bifele root XML:** valorile finale (`bifa121`, `bifa122`, `bifa132`) sunt setate de DUF la re-export, nu de skill. Vezi `references/workflow/duf-roundtrip.md`.

- **`totalPlata_A`:** checksum CNP, nu total fiscal. Nu te alarma că nu corespunde sumei de plată.

- [Alte avertismente specifice sesiunii, ex. "Pierderi reportate din 2024 verificate manual contra D212.xml anterior."]
```

---

## Reguli de generare

1. **Toate variabilele `{...}`** se substituie cu valori reale calculate la Faza 5. Nu lăsa placeholderi în raportul final.

2. **§4 (instrucțiuni manuale) este obligatorie.** Generează un sub-pas (2.a, 2.b, ...) pentru fiecare `<cap14>` din XML, în aceeași ordine ca în XML. Folosește tabel cu coloane `Câmp DUF` | `Valoare`. Marchează câmpurile auto-calculate de DUF cu italic + textul `_auto-calculat de DUF: {valoare}_`.

3. **§3 (CASS) și §4 Pasul 3 (CASS):** dacă CASS = 0, scurtează la o singură propoziție explicând că secțiunea e goală. Nu afișa tabele cu zero peste tot.

4. **§5 (Surse citate):** generează automat din frontmatter-ele `_legi/{an}/*.md` folosite efectiv în calcul. Fiecare fapt are exact o linie în tabel.

5. **§7 (Avertismente):** include cele 3 avertismente standard (metoda și dovezile conversiei, bife, `totalPlata_A`) plus orice altele specifice sesiunii (waivere preflight, asumări de date etc.).

6. **Limba:** română peste tot. Numele coduri de categorie și atributelor XML rămân ca în sursa oficială (ex. `str_categ_venit`, `2012`, `str_dif_impozit_datorat`).

7. **Tonul:** instructional și concret. Utilizatorul deschide raportul lângă browser și-l urmărește linie cu linie. Nu prosă lungă, ci tabele și liste.

8. **Verificare la sfârșit:** validare manuală sumar fiscal skill vs DUF (Pasul 5). Dacă diverg, raportul e greșit — re-calculează.
