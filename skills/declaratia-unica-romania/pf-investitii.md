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

**Toate bifele la `"0"`.** Reguli inițiale ipotetice ("bifa122=1 pentru venituri străinătate", "bifa132=1 pentru CASS investiții") s-au dovedit greșite la testarea cu DUF live — vezi `schema/d212-xml-schema.md` §Mapare bife pentru detalii. DUF rescrie bifele după logică internă la import + re-export. Skill-ul nu încearcă să le seteze.

Procesul corect (vezi `workflow/duf-roundtrip.md`): generăm XML cu toate bifele "0" → import în DUF → re-export → XML-ul DUF este forma canonică.

Verifică restul bifelor în `schema/d212-xml-schema.md` la freshness check.
