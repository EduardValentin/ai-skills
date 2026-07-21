# Schema validator — sync rules

Fișierele `references/schema/d212-xml-schema.md`, `references/schema/form-mapping.yaml` și `references/schema/form-mapping.md` trebuie să rămână sincronizate:

- `references/schema/d212-xml-schema.md` — sursa de adevăr pentru atribute XML, elemente, namespace
- `references/schema/form-mapping.yaml` — sursa structurată pentru mapare categorie ↔ atribute
- `references/schema/form-mapping.md` — narativul companion pentru YAML
- `assets/templates/d212-root.xml`, `assets/templates/cap14-romania.xml`, `assets/templates/cap14-strainatate.xml` și `assets/templates/oblig_realizat.xml` — template-uri parametrizabile

## Reguli stricte

1. **Orice atribut XML adăugat în `references/schema/d212-xml-schema.md` trebuie să apară în template-ul XML relevant** (`assets/templates/d212-root.xml` pentru root, `assets/templates/cap14-romania.xml` și `assets/templates/cap14-strainatate.xml` pentru cap14, `assets/templates/oblig_realizat.xml` pentru obligații).

2. **Orice câmp în `references/schema/form-mapping.yaml` trebuie să aibă descriere în `references/schema/form-mapping.md`.** Reciproc: orice secțiune în md trebuie să corespundă unei intrări YAML.

3. **Schimbarea `schema_namespace` în orice fișier** trebuie propagată în:
   - `references/schema/d212-xml-schema.md` frontmatter
   - `references/schema/form-mapping.yaml` `meta.schema_namespace`
   - `assets/templates/d212-root.xml` element `xmlns` și `xsi:schemaLocation`

4. **Adăugarea unui nou cod de categorie venit** (ex. 2019) cere:
   - Update în `references/schema/d212-xml-schema.md` secțiunea "Codurile de categorie venit"
   - Adăugare în `references/schema/form-mapping.yaml` sub `categorii_venit`
   - Adăugare secțiune dedicată în `references/schema/form-mapping.md`
   - Update în `references/pf-investitii.md` dacă domeniul skill-ului îl folosește

5. **Manifestele de schemă au frontmatter `last_verified` sincronizat.** Runtime-ul nu îl rescrie. O dată divergentă declanșează hard-stop; numai auditul separat din sursa repository-ului poate actualiza atomic manifestele, mapping-urile și template-urile, urmat de review și validare.

## Procedura de re-sincronizare

Când freshness check (Faza 2) detectează schimbare la DUF, sesiunea runtime se oprește. Într-o activitate separată asupra sursei repository-ului:

1. Update `references/schema/d212-xml-schema.md` și `references/schema/duf-platform-structure.md` cu noile valori
2. Compară lista atributelor și codurilor cu `references/schema/form-mapping.yaml`
3. Adăugă/modifică intrările YAML
4. Update `references/schema/form-mapping.md` cu secțiuni / capcane noi
5. Regenerează template-urile XML dacă structura s-a schimbat
6. Rulează review-ul și validarea repository-ului; sesiunea fiscală se reia numai cu o proiecție runtime nouă

## Test manual de sincronizare (opțional, pentru audit)

Scan rapid:

```bash
# 1. Toate codurile din YAML apar în d212-xml-schema.md tabel?
python3 -c "
import yaml, re
m = yaml.safe_load(open('references/schema/form-mapping.yaml'))
yaml_codes = {c['cod'] for c in m['categorii_venit']}
schema_md = open('references/schema/d212-xml-schema.md').read()
schema_codes = set(re.findall(r'\`(\d{4})\`', schema_md))
missing = yaml_codes - schema_codes
extra = schema_codes - yaml_codes
if missing: print('YAML codes missing in schema md:', missing)
if extra: print('schema md codes missing in YAML:', extra)
if not missing and not extra: print('codes in sync')
"
```

Expected: `codes in sync` line.
