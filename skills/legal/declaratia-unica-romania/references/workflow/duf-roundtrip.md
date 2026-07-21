# DUF round-trip — XML canonic

**Regula:** XML-ul generat de skill este *input pentru DUF*, nu produs final. Forma canonică = XML-ul **re-exportat de DUF** după import + salvare.

## De ce

DUF recalculează **silentios** mai multe atribute "tehnice" (de control, nu fiscale) după logică internă nedocumentată. La prima utilizare reală am observat:

| Atribut | Skill a produs | DUF a normalizat la | De ce |
|---|---|---|---|
| `totalPlata_A` | totalul fiscal | suma cifrelor CNP din sesiunea declarantului | Atributul este un checksum CNP, nu valoarea fiscală; vezi `references/schema/d212-xml-schema.md` și template-ul root. |
| `bifa121`, `bifa122`, `bifa132` | bazat pe prezența cap14 cu/fără țară | `bifa121="1"`, `bifa122="0"`, `bifa132="0"` (chiar și cu venituri străinătate prezente) | DUF folosește logică internă despre regim, conformare, CAS estimat etc., nu doar prezența capitolelor. |
| Câmpuri CASS detaliate (`cass_total_ven`, `cass_baza`, `cass_anuala`, `cass_datorat`, `cass_retinut`, `cass_dif_*`, `bifa_cass_*`, `oblcass_real_*`) | trimise mereu | omise când CASS datorată e `0` și nu e activată secțiunea CASS | DUF nu serializează aceste câmpuri pentru sesiunile fără CASS de plată. |

Concluzia: chiar dacă XML-ul nostru e *importabil*, atributele de control diferă de canonic. Pentru audit trail clar și pentru a evita confuzia la control fiscal, **trecem prin DUF după generare**.

## Procedură (după Faza 6 a orchestratorului)

1. **Skill generează `outputs/D212.xml`** cu toate bifele `"0"`, `totalPlata_A = suma cifrelor CNP`, câmpurile CASS condiționate de `cass_due`. Fișierul rămâne candidat pentru import; nu îl descrie drept acceptat până când DUF îl importă efectiv.

2. **Utilizatorul importă în DUF** (`https://www.anaf.ro/declaratii/duf`):
   - "Importă declarație" / "Încarcă XML existent" → selectează `outputs/D212.xml`
   - DUF citește, populează formularul, recalculează silentios atributele de control

3. **Utilizatorul revizuiește în DUF** (eventual face corecții fine) și **descarcă XML-ul re-generat** ("Descarcă XML" / "Exportă").

4. **Salvează re-exportul ca `outputs/D212.canonical.xml`** alături de varianta originală.

5. **Update `raport-completare.md`**:
   - Secțiunea "Avertismente" → adaugă nota: "XML-ul `D212.canonical.xml` este forma re-exportată de DUF după import. Folosește acest fișier pentru submit final, nu `D212.xml`."
   - Secțiunea "Diff canonical vs initial" (opțional) → listează atributele care au fost normalizate de DUF (totalPlata_A, bife, CASS detail). Asta dă audit trail clar despre ce a recalculat DUF.

6. **Worklog entry:**
   ```
   [YYYY-MM-DD HH:MM] duf-roundtrip: import outputs/D212.xml → re-export outputs/D212.canonical.xml. Atribute normalizate de DUF: totalPlata_A, bifa121, bifa122, bifa132[, cass_*].
   ```

## Generare diff atribute (utilitar)

```bash
python3 - <<'PY'
import xml.etree.ElementTree as ET

def attrs(path):
    ns = "{mfp:anaf:dgti:d212:declaratie:v11}"
    root = ET.parse(path).getroot()
    return {k: v for k, v in root.attrib.items()}

a = attrs("outputs/D212.xml")
b = attrs("outputs/D212.canonical.xml")
for k in sorted(set(a) | set(b)):
    if a.get(k) != b.get(k):
        print(f"  {k}: {a.get(k)!r} → {b.get(k)!r}")
PY
```

## Când poate fi omis gate-ul

- Dacă utilizatorul nu intenționează depunere electronică și folosește rezultatele doar pentru calcul, planificare sau completare manuală, round-trip-ul nu este cerut.
- Dacă DUF este indisponibil, `D212.xml` și raportul pot rămâne dovezi de lucru, dar depunerea electronică este blocată. Menționează indisponibilitatea în raport și `worklog.md`; nu propune submit-ul XML-ului brut.

Altfel, round-trip-ul este **obligatoriu** înainte de submit. Consimțământul utilizatorului nu poate elimina acest gate.
