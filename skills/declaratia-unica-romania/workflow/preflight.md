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
