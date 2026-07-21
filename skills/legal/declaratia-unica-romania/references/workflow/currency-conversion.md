# Currency conversion protocol - metoda susținută oficial

Nu există o metodă implicită pentru toate veniturile. Înainte de orice conversie destinată D212, stabilește din dovezi oficiale regula aplicabilă categoriei de venit, anului fiscal, sursei venitului și monedei.

Media anuală poate fi folosită atunci când instrucțiunile sau norma aplicabilă o cer explicit. Cursul BNR din data realizării se folosește atunci când aceasta este regula oficială verificată. `cursbnr.ro`, o medie pe trei date sau preferința utilizatorului nu stabilesc metoda fiscală și nu sunt dovezi pentru valoarea finală.

## Aplicabilitate

- Pentru o sumă documentată deja în RON, nu aplica o conversie suplimentară.
- Pentru orice sumă în valută, tratează separat venitul brut, costul, impozitul reținut și fiecare altă componentă care intră în calcul.
- Nu presupune că toate categoriile sau toate sursele de venit din aceeași sesiune au aceeași regulă.

## Procedură

1. **Identifică faptul de convertit.** Înregistrează categoria de venit, țara sau sursa, moneda, data ori perioada realizării și documentul utilizatorului din care provine suma.

2. **Determină regula oficială.** Verifică pentru anul fiscal relevant, în această ordine:
   - ordinul și instrucțiunile ANAF aplicabile formularului D212;
   - Codul fiscal și normele aplicabile în forma valabilă pentru anul și categoria respectivă, prin `legislatie.just.ro`;
   - publicația sau seria oficială BNR necesară pentru cursul cerut de regula fiscală și, numai dacă regula cere o conversie intermediară pentru o monedă necotată de BNR, sursa oficială a autorității monetare relevante.

3. **Creează sau re-verifică `_legi/{an}/conversie-valutara.md`.** Pentru fiecare categorie folosită, păstrează cel puțin:

   ```yaml
   categorie_venit: <categorie>
   an_fiscal: <YYYY>
   metoda: <curs_mediu_anual_bnr | curs_bnr_data_realizarii | alta_metoda_oficiala>
   granularitate: <total_anual | data_realizarii | alta>
   source_url_regula: <URL oficial>
   source_anchor_or_excerpt: <articol, punct sau extras scurt>
   source_url_curs: <URL oficial al autorității cerute de regulă>
   source_authority_curs: <BNR | altă autoritate monetară oficială cerută>
   accessed_on: <YYYY-MM-DD>
   last_verified: <YYYY-MM-DD>
   ```

4. **Aplică hard-gate-ul de dovezi.** Dacă sursa oficială nu determină clar metoda sau dacă modulul cache nu leagă metoda de categoria și anul curent, oprește calculul destinat depunerii. Spune ce regulă lipsește și ce sursă oficială trebuie verificată; nu înlocui dovada cu un site agregator sau cu alegerea utilizatorului.

5. **Preia fiecare curs din autoritatea oficială cerută de regulă.** Orice curs BNR provine direct dintr-o publicație sau serie BNR. Dacă regula verificată cere o conversie intermediară pentru o monedă necotată de BNR, folosește sursa oficială indicată de acea regulă. Păstrează autoritatea, URL-ul, data accesării, moneda, data sau anul cursului și valoarea exactă în modulul cache.

6. **Calculează la granularitatea cerută:**

   ```text
   dacă metoda = curs_bnr_data_realizarii:
     suma_RON_linie = rotunjire_conform_regulii(suma_valuta_linie * curs_BNR_data_linie)
     suma_RON = suma(suma_RON_linie)

   dacă metoda = curs_mediu_anual_bnr:
     suma_RON = rotunjire_conform_regulii(suma_valuta_eligibila * curs_mediu_anual_BNR)
   ```

   Regula de rotunjire trebuie și ea susținută de instrucțiunile aplicabile sau de comportamentul DUF verificat; nu o presupune din exemplul de mai sus.

7. **Separă comparațiile de valoarea fiscală.** O metodă alternativă poate apărea în raport numai ca estimare comparativă etichetată clar. Nu o transfera în câmpurile D212 decât dacă există dovadă oficială aplicabilă.

## Loguri

Fiecare conversie folosită în calcul se înregistrează în `worklog.md` cu proveniența metodei și a cursului:

```text
[YYYY-MM-DD HH:MM] currency-convert: category=<>, amount=<valoare moneda>, method=<>, rate=<>, rate_date_or_year=<>, result_RON=<>, rule_ref=_legi/{an}/conversie-valutara.md#<ancora>, input_ref=<fișier:pagină/rând>
```
