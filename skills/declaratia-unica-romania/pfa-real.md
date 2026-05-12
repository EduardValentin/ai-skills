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

**Toate bifele la `"0"`.** La testarea cu DUF live pentru PF investiții, regulile inițiale despre bife (de ex. "bifa122=1 pentru străinătate") s-au dovedit greșite. Probabilitate similară pentru PFA — DUF rescrie bifele după logică internă. Skill-ul nu încearcă să le seteze, ci se bazează pe **DUF round-trip** (vezi `workflow/duf-roundtrip.md`): importăm XML-ul cu bifele "0" în DUF, lăsăm DUF să normalizeze, re-exportăm — XML-ul re-exportat e forma canonică.

Excepție: `bifa_cass_real` / `bifa_cass_datorat_*` din `<oblig_realizat>` rămân setate explicit pentru că definesc regimul CASS, nu un capitol; vezi mai jos.

## Atribute `<oblig_realizat>` specifice PFA

Pe lângă cele comune cu PF investiții, pentru PFA real intervin:

- `oblimpoz_real_total`, `oblimpoz_real_dif_deplata`, `oblimpoz_real_dif_restituit`
- `oblcas_real_difPlus`, `oblcas_real_str`
- `bifa_cass_real = "1"` (regim real CASS)
- `bifa_cass_datorat_dpi = "0"` (nu DPI)
- `bifa_cass_datorat_ai = "1"` (activități independente)
