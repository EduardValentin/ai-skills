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
