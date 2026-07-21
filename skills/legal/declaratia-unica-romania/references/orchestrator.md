# Orchestrator — Declarația Unică România

Documentul descrie cele 8 faze ale workflow-ului, fiecare cu hard-gate. Acest fișier e citit imediat după `SKILL.md` la începutul oricărei sesiuni.

## Definiții

- **Hard-gate**: agentul NU execută acțiuni din faza următoare până condiția gate-ului curent nu e satisfăcută explicit. Nu există fallback tăcut, default-uri implicite sau "presupun că e OK". La blocaj: agent listează ce lipsește și așteaptă input.
- **Ultima sesiune detectabilă**: după confirmarea declarantului și a slug-ului, cel mai recent folder cu format `YYYY-MM-DD_{persoana_slug}` găsit numai sub `${D212_DATA_DIR}/*/sesiuni/`, indiferent de an fiscal.

## Phase 1 — Identificare sesiune

**Gate:** nume declarant + slug + an fiscal + categorii PF confirmate; abia apoi sesiunea existentă selectată sau folderul nou creat.

Întrebări obligatorii (în această ordine):

1. "Pentru cine completezi declarația? Spune numele complet al declarantului."
   - Un răspuns precum "pentru mine" nu identifică persoana; cere numele complet, fără să-l deduci din cont, mediu, calea locală sau sesiuni anterioare.
   - Propune un slug derivat din numele confirmat (lowercase, spații înlocuite cu `-`, diacritice eliminate) și cere confirmarea explicită a numelui și slug-ului.
   - Nu lista, nu selecta și nu crea nicio sesiune înainte de această confirmare. După confirmare, reluarea caută numai `${D212_DATA_DIR}/*/sesiuni/YYYY-MM-DD_{persoana_slug}`.

2. "Care e anul fiscal declarat? (default: anul calendaristic precedent — {YYYY-1})"
   - Anul fiscal = anul ale cărui venituri se declară (ex. 2025 pentru declarația depusă în 2026)

3. "Ce categorii de venituri PF verificăm?"
   - dividende, câștiguri din transferul titlurilor sau alte instrumente financiare, dobânzi ori cripto;
   - una sau mai multe categorii, cu inputuri și calcule păstrate distinct.

Pentru o cerere PFA, oprește înainte de sesiune, calcul sau output. Explică faptul că mapping-ul și template-urile PFA nu sunt acoperite de acest skill și redirecționează utilizatorul către asistență fiscală adecvată.

**Acțiuni la pass:**
- După confirmarea identității, caută numai sesiuni care corespund slug-ului în `${D212_DATA_DIR}/*/sesiuni/YYYY-MM-DD_{persoana_slug}`. Dacă există una relevantă, cere utilizatorului să aleagă explicit reluarea sau crearea unei sesiuni noi.
- Pentru o sesiune nouă, creează `${D212_DATA_DIR}/{an_fiscal}/sesiuni/{YYYY-MM-DD}_{persoana_slug}/` cu subfoldere `inputs/` și `outputs/`.
- Creează `worklog.md` în folderul sesiunii cu primul entry:
  ```
  [YYYY-MM-DD HH:MM] session-start: persoana=<slug>, an_fiscal=<an>, categorii_pf=<list>, agent=<claude|codex>
  ```
- Confirmă crearea cu utilizatorul și listează path-ul.

## Phase 2 — Freshness check schema

**Gate:** `references/schema/d212-xml-schema.md` și `references/schema/duf-platform-structure.md` au `last_verified < 30 zile` (skip) SAU verificarea oficială dovedește că versiunea și structura sunt neschimbate, iar dovada este înregistrată numai în sesiune.

Procedură: vezi `references/workflow/freshness-check.md`.

Hard-stop la orice schimbare de versiune, namespace, structură, secțiuni, butoane sau template → notifică utilizatorul, oprește sesiunea curentă și cere audit separat în sursa repository-ului, validare și o proiecție runtime nouă.

## Phase 3 — Cache legi check

**Gate:** modulele relevante categoriilor PF au `last_verified < 90 zile`.

Pentru categoriile PF active, verifică modulele relevante din `_legi/{an}/`: `impozit-dividende.md`, `impozit-castig-capital.md`, `impozit-dobanzi.md`, `impozit-cripto.md`, `tratate-dubla-impunere.md`, `conversie-valutara.md`, `plafoane-cass.md` și `salariu-minim.md`.

Folder `_legi/{an}/` lipsă → refresh complet al modulelor relevante. Pentru metoda și cursul valutar, urmează `references/workflow/currency-conversion.md`; nu presupune media anuală sau o sursă neoficială.

La pass, log:
```
[YYYY-MM-DD HH:MM] cache-check: categorii_pf=<>, modules_verified=<count>, refreshed=<count>
```

## Phase 4 — Preflight documente

**Gate:** toate documentele obligatorii sunt prezente în `inputs/` SAU au waiver documentat.

Procedură: vezi `references/workflow/preflight.md`. Lista per categorie este în `references/pf-investitii.md`.

Hard-stop până PASS.

## Phase 5 — Calcul + citare

**Gate:** worklog conține câte un entry pentru fiecare linie cap14 + oblig_realizat cu raw / cite / computed.

Urmează `references/pf-investitii.md#proceduri-calcul`. Disciplina de citare este în `references/workflow/citation-protocol.md`.

Conversie valutară: `references/workflow/currency-conversion.md`.

La pass, log:
```
[YYYY-MM-DD HH:MM] calculations-done: cap14_lines=<count>, total_dif_de_plata=<RON>, total_dif_de_restituit=<RON>
```

## Phase 6 — Generare output

**Gate:** `outputs/D212.xml` generat și validat structural; `outputs/raport-completare.md` complet.

Procedură generare XML:
1. Citește `assets/templates/d212-root.xml` ca shell.
2. Instanțiază `assets/templates/oblig_realizat.xml` cu valorile din `<oblig_realizat>` calculate la Faza 5.
3. Pentru fiecare linie cap14, instanțiază `assets/templates/cap14-strainatate.xml` sau `assets/templates/cap14-romania.xml`.
4. Substituie placeholderii `{{...}}` cu valori reale; gestionează `{{#if X}}...{{/if}}` ca render condițional.
5. Concatenează în `assets/templates/d212-root.xml` substituind `{{oblig_realizat_block}}` și `{{cap14_blocks}}`.
6. Scrie `outputs/D212.xml`.

Validare structurală:
```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('outputs/D212.xml'); print('XML valid')"
```

Hard-stop pe eroare.

Procedură generare raport: urmează **strict** `references/workflow/raport-template.md`. Secțiunile sunt obligatorii, nu opționale:

1. Frontmatter cu persoană, an fiscal, categorii PF, agent, metoda de conversie susținută oficial și `platform_version` DUF
2. **Sumar fiscal** — tabel cu impozit, CAS, CASS, diferență de plată
3. **Detalii per linie de venit** — pentru fiecare cap14: raw input, conversie, citații lege, calcul pas cu pas
4. **Instrucțiuni completare manuală în DUF** — pas-cu-pas în browser pe `duf.anaf.ro`: pentru fiecare cap14, tabel `Câmp DUF | Valoare` cu valorile concrete pe care utilizatorul le introduce; câmpurile auto-calculate de DUF marcate cu italic. Aceasta este secțiunea principală a raportului — utilizatorul ține raportul deschis lângă browser și completează linie cu linie.
5. Surse citate (URL + accessed_on per fapt)
6. Pași finali (DUF round-trip, submit SPV, plată)
7. Avertismente (metodă de conversie și dovezi, bife, `totalPlata_A`, asumări specifice)

Hard-stop la generare raport dacă §4 nu conține un sub-pas dedicat pentru fiecare `<cap14>` din XML. Lipsa instrucțiunilor manuale face raportul inutilizabil pentru completare in-browser.

## Phase 6.5 — DUF round-trip (forma canonică)

**Gate obligatoriu pentru depunere electronică:** există `outputs/D212.canonical.xml` re-exportat din DUF după importul și revizuirea `outputs/D212.xml`.

XML-ul generat este numai candidat de import, nu formă canonică. DUF poate normaliza `totalPlata_A`, bifele și câmpurile CASS detaliate după logică internă; treci prin DUF înainte de submit.

Procedură: vezi `references/workflow/duf-roundtrip.md`. Pe scurt: utilizatorul importă `D212.xml` în `duf.anaf.ro`, lasă DUF să normalizeze, exportă XML-ul re-generat ca `D212.canonical.xml`. Skill-ul rulează diff-ul de atribute și actualizează `raport-completare.md` cu lista normalizărilor.

Gate-ul poate fi omis numai dacă nu există intenție de depunere electronică. Dacă DUF este indisponibil, activitățile de calcul, raportare și review pot continua, dar sesiunea este blocată de la submit; consemnează motivul în `worklog.md`. Consimțământul utilizatorului nu permite depunerea XML-ului brut.

## Phase 7 — Review utilizator

**Gate:** user răspunde "OK" sau cere corecție.

Prezintă summary:
```
Sesiunea pentru {persoana}, an fiscal {an}, categorii PF {list}.

Sumar fiscal:
- Impozit pe venit total: {X} RON
- CAS total: {Y} RON
- CASS total: {Z} RON
- Diferență de plată / restituit: {W} RON

Detalii complete: outputs/raport-completare.md
XML candidat pentru import și revizuire în DUF: outputs/D212.xml
XML eligibil pentru submit electronic: outputs/D212.canonical.xml sau BLOCAT până la round-trip

Vrei să revizuim ceva specific sau confirmi sesiunea?
```

Așteaptă răspuns. Corecție → întoarcere la Phase 5 cu modificarea înregistrată în worklog. OK → Phase 8.

## Phase 8 — Închidere sesiune

Log final în worklog:
```
[YYYY-MM-DD HH:MM] session-close: status=OK, outputs_path=<>, dif_de_plata=<RON>
```

Anunță user:
```
Sesiunea închisă. Artefacte salvate la:
- ${D212_DATA_DIR}/{an}/sesiuni/{YYYY-MM-DD}_{slug}/outputs/D212.xml
- ${D212_DATA_DIR}/{an}/sesiuni/{YYYY-MM-DD}_{slug}/outputs/D212.canonical.xml (numai după round-trip)
- ${D212_DATA_DIR}/{an}/sesiuni/{YYYY-MM-DD}_{slug}/outputs/raport-completare.md
- ${D212_DATA_DIR}/{an}/sesiuni/{YYYY-MM-DD}_{slug}/worklog.md

Pași următori pentru tine:
1. Citește `raport-completare.md` și verifică sumarul fiscal.
2. Importă `D212.xml` în https://www.anaf.ro/declaratii/duf (sau completează manual urmând secțiunea "Instrucțiuni completare manuală" din raport), revizuiește și re-exportă `D212.canonical.xml`.
3. Pentru depunere electronică, încarcă numai `D212.canonical.xml` prin SPV. Dacă DUF nu a putut re-exporta fișierul, nu depune XML-ul brut.
4. Plătește diferența la cont ANAF (vezi instrucțiuni anuale pentru cont destinație).
```
