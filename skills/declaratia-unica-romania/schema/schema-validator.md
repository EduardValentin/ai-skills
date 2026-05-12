# Schema validator — sync rules

Cele trei fișiere din `schema/` trebuie să rămână sincronizate:

- `d212-xml-schema.md` — sursa de adevăr pentru atribute XML, elemente, namespace
- `form-mapping.yaml` — sursa structurată pentru mapare categorie ↔ atribute
- `form-mapping.md` — narativul companion pentru YAML
- `templates/*.xml` — template-uri parametrizabile

## Reguli stricte

1. **Orice atribut XML adăugat în `d212-xml-schema.md` trebuie să apară în template-ul XML relevant** (`templates/d212-root.xml` pentru root, `templates/cap14-*.xml` pentru cap14, `templates/oblig_realizat.xml` pentru obligații).

2. **Orice câmp în `form-mapping.yaml` trebuie să aibă descriere în `form-mapping.md`.** Reciproc: orice secțiune în md trebuie să corespundă unei intrări YAML.

3. **Schimbarea `schema_namespace` în orice fișier** trebuie propagată în:
   - `d212-xml-schema.md` frontmatter
   - `form-mapping.yaml` `meta.schema_namespace`
   - `templates/d212-root.xml` element `xmlns` și `xsi:schemaLocation`

4. **Adăugarea unui nou cod de categorie venit** (ex. 2019) cere:
   - Update în `d212-xml-schema.md` secțiunea "Codurile de categorie venit"
   - Adăugare în `form-mapping.yaml` sub `categorii_venit`
   - Adăugare secțiune dedicată în `form-mapping.md`
   - Update în `pf-investitii.md` sau `pfa-real.md` dacă scenariul îl folosește

5. **Toate fișierele schema au frontmatter `last_verified`** care se actualizează atomic la freshness check. Dacă unul are dată mai veche decât altele, e desincronizare — declanșează re-verificare manuală.

## Procedura de re-sincronizare

Când freshness check (Faza 2) detectează schimbare la DUF:

1. Update `d212-xml-schema.md` și `duf-platform-structure.md` cu noile valori
2. Compară lista atributelor și codurilor cu `form-mapping.yaml`
3. Adăugă/modifică intrările YAML
4. Update `form-mapping.md` cu secțiuni / capcane noi
5. Regenerează template-urile XML dacă structura s-a schimbat
6. Run `_sync.sh pull <agent>` pentru a propaga în repo + celălalt install dir
7. Commit + push

## Test manual de sincronizare (opțional, pentru audit)

Scan rapid:

```bash
# 1. Toate codurile din YAML apar în d212-xml-schema.md tabel?
python3 -c "
import yaml, re
m = yaml.safe_load(open('claude/skills/declaratia-unica-romania/schema/form-mapping.yaml'))
yaml_codes = {c['cod'] for c in m['categorii_venit']}
schema_md = open('claude/skills/declaratia-unica-romania/schema/d212-xml-schema.md').read()
schema_codes = set(re.findall(r'\`(\d{4})\`', schema_md))
missing = yaml_codes - schema_codes
extra = schema_codes - yaml_codes
if missing: print('YAML codes missing in schema md:', missing)
if extra: print('schema md codes missing in YAML:', extra)
if not missing and not extra: print('codes in sync')
"
```

Expected: `codes in sync` line.
