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
