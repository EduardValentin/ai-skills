# Freshness check protocol

Rulează la Faza 2 a sesiunii. Verifică dacă cunoștințele statice ale skill-ului (schema XML, structura DUF) sunt actuale.

## Trigger

Citește frontmatter din:
- `schema/d212-xml-schema.md`
- `schema/duf-platform-structure.md`

Pentru fiecare, calculează `today - last_verified`.

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

4. **Compară cu frontmatter:**

   | Caz | Acțiune |
   |---|---|
   | `platform_version` identic | bump `last_verified` în ambele frontmatter-uri la today; commit în repo canonic + `_sync.sh push` |
   | Patch version diferit (V-1.8.08 → V-1.8.09) | (a) fetch din nou Instrucțiuni PDF anuale; (b) confirmă că coduri categorie 2012/2017/2018 + atributele cap14 + atributele oblig_realizat sunt neschimbate; (c) update `platform_version` și `last_verified`; (d) commit + sync |
   | Minor diferit (V-1.8.x → V-1.9.x) | hard-stop. Notifică user: "Schema DUF s-a schimbat de la V-1.8.x la V-1.9.x. Trebuie audit manual al `form-mapping.yaml`, `form-mapping.md`, și template-urilor XML." Cere user confirmation să pornească o sub-sarcină de update; nu continuă sesiunea curentă. |
   | Major sau namespace diferit | hard-stop. Update manual obligatoriu pentru toate fișierele schema/ și template-urile. |
   | Lista secțiunilor sau butoanelor schimbată | hard-stop. Update `duf-platform-structure.md` cu noile valori înainte de a continua. |

5. **După update reușit:**
   - Dacă modificarea s-a făcut direct în skill-ul canonic (`<repo>/skills/declaratia-unica-romania/schema/`): `git add` + commit, apoi `_sync.sh push` ca să propage la ambele install dirs.
   - Dacă modificarea s-a făcut într-un install dir runtime (`~/.<agent>/skills/.../schema/`): `_sync.sh pull <agent>` propagă în canonic + celălalt install dir, apoi commit din repo. Vezi `../_sync.sh` pentru sub-comenzi.
   - Anunță user: "Schema actualizată la V-x.y.z. Continuă sesiunea."

## Loguri

Toate verificările (skip sau update) se înregistrează în `worklog.md` din sesiunea curentă, cu format:

```
[YYYY-MM-DD HH:MM] freshness-check: schema last_verified=YYYY-MM-DD, age=N days, action=skip|update, platform_version_old=Vx.y.z, platform_version_new=Vx.y.z
```
