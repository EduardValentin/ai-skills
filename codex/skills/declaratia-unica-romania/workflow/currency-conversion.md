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
