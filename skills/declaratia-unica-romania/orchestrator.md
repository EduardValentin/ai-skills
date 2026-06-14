# Orchestrator — Declarația Unică România

Documentul descrie cele 8 faze ale workflow-ului, fiecare cu hard-gate. Acest fișier e citit imediat după `SKILL.md` la începutul oricărei sesiuni.

## Definiții

- **Hard-gate**: agentul NU execută acțiuni din faza următoare până condiția gate-ului curent nu e satisfăcută explicit. Nu există fallback tăcut, default-uri implicite sau "presupun că e OK". La blocaj: agent listează ce lipsește și așteaptă input.
- **Ultima sesiune detectabilă**: cel mai recent folder cu format `YYYY-MM-DD_*` găsit în `declaratii-unice/*/sesiuni/`, indiferent de an fiscal.

## Phase 1 — Identificare sesiune

**Gate:** persoană + an fiscal + scenarii confirmate; folder sesiune creat.

Întrebări obligatorii (în această ordine):

1. "Pentru cine completezi declarația? (default: pentru tine — Eduard Trocan)"
   - Dacă self: `persoana_slug = eduard-trocan`
   - Altcineva: cere nume complet, slugifică (lowercase, înlocuiește spații cu `-`, elimină diacritice)

2. "Care e anul fiscal declarat? (default: anul calendaristic precedent — {YYYY-1})"
   - Anul fiscal = anul ale cărui venituri se declară (ex. 2025 pentru declarația depusă în 2026)

3. "Ce scenarii rulăm? (PF investiții / PFA real / ambele)"
   - PF investiții — dividende, câștig capital, dobânzi, cripto, alte instrumente financiare
   - PFA real — venit PFA în sistem real (NU norma de venit)
   - Ambele — output unificat

Pentru răspunsuri care aleg clar doar **PFA real**, confirmă scenariul PFA real și cere documentele PFA relevante. Nu enumera exemple, documente, cache-uri sau liste din PF investiții în aceeași întrebare; dacă trebuie verificat dacă mai există alte scenarii, întreabă generic dacă există și alte venituri care ar schimba scenariul.

**Acțiuni la pass:**
- Creează `/Users/trocaneduard/Documents/Personal/declaratii-unice/{an_fiscal}/sesiuni/{YYYY-MM-DD}_{persoana_slug}/` cu subfoldere `inputs/` și `outputs/`.
- Creează `worklog.md` în folderul sesiunii cu primul entry:
  ```
  [YYYY-MM-DD HH:MM] session-start: persoana=<slug>, an_fiscal=<an>, scenarii=<list>, agent=<claude|codex>
  ```
- Confirmă cu user creearea, listează path-ul.

## Phase 2 — Freshness check schema

**Gate:** `schema/*.md` au `last_verified < 30 zile` (skip) SAU au fost actualizate față de DUF live (update + sync).

Procedură: vezi `workflow/freshness-check.md`.

Hard-stop pe minor/major/namespace change → notifică user, oprește sesiunea curentă, propune sub-sarcină de audit.

## Phase 3 — Cache legi check

**Gate:** modulele relevante scenariilor au `last_verified < 90 zile`.

Pentru fiecare scenariu activ:

- **PF investiții** → verifică `_legi/{an}/{impozit-dividende,impozit-castig-capital,impozit-dobanzi,impozit-cripto,tratate-dubla-impunere,curs-bnr-mediu,plafoane-cass,salariu-minim}.md`.
- **PFA real** → verifică `_legi/{an}/{pfa-real-cheltuieli,plafoane-cas,plafoane-cass,salariu-minim,modificari-cf-fata-de-anul-precedent}.md`.

Folder `_legi/{an}/` lipsă → refresh complet (toate modulele scenariului). Pentru cursul valutar V2: folosește `workflow/currency-conversion.md`.

La pass, log:
```
[YYYY-MM-DD HH:MM] cache-check: scenario=<>, modules_verified=<count>, refreshed=<count>
```

## Phase 4 — Preflight documente

**Gate:** toate documentele obligatorii sunt prezente în `inputs/` SAU au waiver documentat.

Procedură: vezi `workflow/preflight.md`. Lista per scenariu e în `pf-investitii.md` / `pfa-real.md`.

Hard-stop până PASS.

## Phase 5 — Calcul + citare

**Gate:** worklog conține câte un entry pentru fiecare linie cap14 + oblig_realizat cu raw / cite / computed.

Pentru fiecare scenariu, urmează procedura din scenariu file (`pf-investitii.md#proceduri-calcul` sau `pfa-real.md#proceduri-calcul`). Disciplina de citare: vezi `workflow/citation-protocol.md`.

Conversie valutară: `workflow/currency-conversion.md`.

La pass, log:
```
[YYYY-MM-DD HH:MM] calculations-done: cap14_lines=<count>, total_dif_de_plata=<RON>, total_dif_de_restituit=<RON>
```

## Phase 6 — Generare output

**Gate:** `outputs/D212.xml` generat și validat structural; `outputs/raport-completare.md` complet.

Procedură generare XML:
1. Citește `schema/templates/d212-root.xml` ca shell.
2. Instanțiază `oblig_realizat.xml` cu valorile din `<oblig_realizat>` calculate la Faza 5.
3. Pentru fiecare linie cap14, instanțiază `cap14-strainatate.xml` sau `cap14-romania.xml`.
4. Substituie placeholderii `{{...}}` cu valori reale; gestionează `{{#if X}}...{{/if}}` ca render condițional.
5. Concatenează în `d212-root.xml` substituind `{{oblig_realizat_block}}` și `{{cap14_blocks}}`.
6. Scrie `outputs/D212.xml`.

Validare structurală:
```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('outputs/D212.xml'); print('XML valid')"
```

Hard-stop pe eroare.

Procedură generare raport: urmează **strict** `workflow/raport-template.md`. Secțiunile sunt obligatorii, nu opționale:

1. Frontmatter cu persoană, an fiscal, scenarii, agent, conversie V2, platform_version DUF
2. **Sumar fiscal** — tabel cu impozit, CAS, CASS, diferență de plată
3. **Detalii per linie de venit** — pentru fiecare cap14: raw input, conversie, citații lege, calcul pas cu pas
4. **Instrucțiuni completare manuală în DUF** — pas-cu-pas în browser pe `duf.anaf.ro`: pentru fiecare cap14, tabel `Câmp DUF | Valoare` cu valorile concrete pe care utilizatorul le introduce; câmpurile auto-calculate de DUF marcate cu italic. Aceasta este secțiunea principală a raportului — utilizatorul ține raportul deschis lângă browser și completează linie cu linie.
5. Surse citate (URL + accessed_on per fapt)
6. Pași finali (DUF round-trip, submit SPV, plată)
7. Avertismente (V2, bife, totalPlata_A, asumări specifice)

Hard-stop la generare raport dacă §4 nu conține un sub-pas dedicat pentru fiecare `<cap14>` din XML. Lipsa instrucțiunilor manuale face raportul inutilizabil pentru completare in-browser.

## Phase 6.5 — DUF round-trip (forma canonică)

**Gate (recomandat, nu strict obligatoriu):** există `outputs/D212.canonical.xml` re-exportat din DUF după importul `outputs/D212.xml`.

XML-ul nostru e *importabil* dar nu *canonic* — DUF normalizează silentios `totalPlata_A`, bifele, și câmpurile CASS detaliate după logică internă. Pentru audit trail clar la control fiscal, treci prin DUF înainte de submit.

Procedură: vezi `workflow/duf-roundtrip.md`. Pe scurt: utilizatorul importă `D212.xml` în `duf.anaf.ro`, lasă DUF să normalizeze, exportă XML-ul re-generat ca `D212.canonical.xml`. Skill-ul rulează diff-ul de atribute și actualizează `raport-completare.md` cu lista normalizărilor.

Skip permis dacă: nu există intenție de submit electronic; DUF e indisponibil; user-ul confirmă explicit (waiver în worklog).

## Phase 7 — Review utilizator

**Gate:** user răspunde "OK" sau cere corecție.

Prezintă summary:
```
Sesiunea pentru {persoana}, an fiscal {an}, scenarii {list}.

Sumar fiscal:
- Impozit pe venit total: {X} RON
- CAS total: {Y} RON
- CASS total: {Z} RON
- Diferență de plată / restituit: {W} RON

Detalii complete: outputs/raport-completare.md
XML pentru import DUF: outputs/D212.xml

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
- {an}/sesiuni/{slug}/outputs/D212.xml
- {an}/sesiuni/{slug}/outputs/raport-completare.md
- {an}/sesiuni/{slug}/worklog.md

Pași următori pentru tine:
1. Citește `raport-completare.md` și verifică sumarul fiscal.
2. Importă `D212.xml` în https://www.anaf.ro/declaratii/duf (sau completează manual urmând secțiunea "Instrucțiuni completare manuală" din raport).
3. Submit electronic prin SPV cu certificat / credențiale.
4. Plătește diferența la cont ANAF (vezi instrucțiuni anuale pentru cont destinație).
```
