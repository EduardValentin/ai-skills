# Freshness check protocol

Rulează la Faza 2 a sesiunii. Verifică dacă cunoștințele statice ale skill-ului (schema XML, structura DUF) sunt actuale.

## Trigger

Citește frontmatter din:
- `references/schema/d212-xml-schema.md`
- `references/schema/duf-platform-structure.md`

Confirmă mai întâi că ambele manifeste au `last_verified` și același `platform_version`, iar manifestul XML are `schema_namespace`. Un câmp lipsă sau valori divergente produc hard-stop. Apoi calculează `today - last_verified` pentru fiecare manifest.

- **< 30 zile** → skip, continuă cu Faza 3.
- **≥ 30 zile** → rulează verificarea.

## Procedură

1. **Fetch pagina DUF** (`https://www.anaf.ro/declaratii/duf`). Fallback ladder pentru obținerea conținutului:
   - (a) tool nativ de web-fetch al agentului, dacă există (preferat — gestionează automat HTTPS, redirects, decodare HTML);
   - (b) `curl -fsSL "https://www.anaf.ro/declaratii/duf" -o /tmp/duf.html` din shell, apoi citește fișierul;
   - (c) `wget -qO- "https://www.anaf.ro/declaratii/duf"` ca alternativă la curl;
   - (d) cere utilizatorului să deschidă URL-ul în browser și să lipească conținutul relevant — doar ca ultim recurs.

2. **Extrage `platform_version`.** E în footer-ul paginii, format `V-x.y.z / DD.MM.YYYY`.

3. **Extrage lista secțiunilor.** Trebuie să fie cele 5 secțiuni cunoscute (Date identificare, Venituri realizate, Venituri cu reținere la sursă, CAS, CASS) plus butoanele "Adaugă venit străinătate/România".

4. **Verifică schema din materialul oficial curent.** Urmează linkurile oficiale DUF către instrucțiunile anuale și orice schemă, exemplu sau export oficial disponibil. Compară namespace-ul, codurile, elementele și atributele folosite de mapping-uri și template-uri. Dacă materialul oficial disponibil nu permite confirmarea unei valori necesare, tratează rezultatul ca necunoscut și aplică hard-stop; nu deduce că structura este neschimbată doar din UI.

5. **Compară cu frontmatter, fără să modifici materialul instalat:**

   | Caz | Acțiune |
   |---|---|
   | `platform_version`, namespace, secțiuni, butoane și structură identice | Înregistrează data, URL-urile și valorile observate numai în `worklog.md`; continuă cu Faza 3. Nu rescrie `last_verified`. |
   | Orice versiune diferită, inclusiv patch (de ex. V-1.8.08 → V-1.8.09) | Hard-stop. Cere un audit separat în sursa repository-ului pentru manifeste, mapping-uri și template-uri; sesiunea fiscală nu continuă. |
   | Namespace diferit sau necunoscut | Hard-stop și același audit separat complet. |
   | Lista secțiunilor, butoanelor, structura sau template-urile diferă | Hard-stop și același audit separat complet. |

6. **La orice schimbare:** nu edita `SKILL.md`, `references/` sau `assets/` din proiecția runtime. Auditul separat trebuie să actualizeze, după caz, `references/schema/d212-xml-schema.md`, `references/schema/duf-platform-structure.md`, `references/schema/form-mapping.yaml`, `references/schema/form-mapping.md`, `assets/templates/d212-root.xml`, `assets/templates/cap14-romania.xml`, `assets/templates/cap14-strainatate.xml` și `assets/templates/oblig_realizat.xml`, apoi să treacă prin review și validare. Sesiunea fiscală poate fi reluată numai dintr-o proiecție runtime nouă a sursei validate.

## Loguri

Toate verificările se înregistrează în `worklog.md` din sesiunea curentă, cu format:

```
[YYYY-MM-DD HH:MM] freshness-check: manifest_last_verified=YYYY-MM-DD, checked_on=YYYY-MM-DD, age=N days, action=skip|verified-unchanged|hard-stop, platform_version_manifest=Vx.y.z, platform_version_observed=Vx.y.z, evidence_urls=<lista>
```
