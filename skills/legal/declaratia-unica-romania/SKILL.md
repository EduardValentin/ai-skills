---
name: declaratia-unica-romania
description: "Use when utilizatorul cere pregătirea sau verificarea Declarației Unice D212 pentru venituri PF din dividende, câștiguri de capital, cripto ori dobânzi. Nu se folosește pentru PFA, firme, salarii, chirii, control fiscal sau contestații."
compatibility: >-
  Requires a user-selected writable D212_DATA_DIR, shell access, Python 3 for local XML well-formedness checks, and network access to official Romanian sources. Use a native web-fetch tool when available, then curl, wget, or user-provided public content. Isolated dispatch is optional; use separate CLI sessions otherwise. DUF import and export remain user-mediated.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Declarația Unică România

## Scop

Orchestrează pregătirea anuală a D212 în română, cu surse oficiale, date separate pe persoană și un traseu auditabil. Produce un raport de completare și, când datele și schema permit, un XML candidat pentru import în DUF. Nu prezenta un calcul drept cert sau un XML drept acceptat înainte de verificările aplicabile.

## Domeniu

Folosește skill-ul pentru:

- venituri PF din dividende, transfer de titluri, cripto sau dobânzi;
- un caz care combină două sau mai multe dintre aceste categorii de venituri PF.

Nu îl activa inițial pentru PFA în sistem real sau la normă de venit, SRL/microîntreprindere, salarii, chirii, control fiscal ori contestații. Dacă un domeniu exclus este descoperit într-o sesiune deja începută, oprește înainte de calcul, păstrează separat dovezile deja primite, explică limita și redirecționează utilizatorul către ajutor adecvat; această ieșire sigură nu extinde domeniul skill-ului.

## Contracte Canonice

Regulile de mai jos prevalează asupra default-urilor, exemplelor numerice sau instrucțiunilor incompatibile din referințele bundle-uite.

1. **Identitate și izolare.** Întreabă pentru cine se pregătește declarația; nu presupune nicio identitate. Confirmă numele și slug-ul înainte de a crea sesiunea. Worklog-ul, XML-urile, raportul, CNP-ul, IBAN-ul și toate inputurile rămân numai în sesiunea acelei persoane.

2. **Layout unic.** Sesiunea canonică este `${D212_DATA_DIR}/{an_fiscal}/sesiuni/{YYYY-MM-DD}_{persoana_slug}/`, cu `inputs/`, `outputs/` și `worklog.md`. Reluarea caută numai `${D212_DATA_DIR}/*/sesiuni/YYYY-MM-DD_*`; nu folosi un prefix suplimentar sau un folder generic.

3. **Skill read-only la runtime.** `SKILL.md`, `references/` și `assets/` sunt material instalat și nu se modifică în timpul unei sesiuni fiscale. Orice schimbare de schemă cere un hard-stop și o activitate separată în sursa repository-ului, urmată de review, validare și o proiecție runtime nouă.

4. **Freshness exact.** Manifestele gate-ului sunt `references/schema/d212-xml-schema.md` și `references/schema/duf-platform-structure.md`; ambele trebuie să aibă același `platform_version` și câmp `last_verified`, iar primul trebuie să aibă `schema_namespace`. Câmp lipsă, valori divergente sau vechime de cel puțin 30 de zile impun verificare oficială. Dacă versiunea și structura sunt neschimbate, înregistrează verificarea curentă în sesiune fără a rescrie skill-ul. Orice schimbare de `platform_version`, namespace, structură, secțiuni, butoane sau template impune hard-stop și audit separat pentru cele două manifeste, `references/schema/form-mapping.yaml`, `references/schema/form-mapping.md`, `assets/templates/d212-root.xml`, `assets/templates/cap14-romania.xml`, `assets/templates/cap14-strainatate.xml` și `assets/templates/oblig_realizat.xml`.

5. **Fapte fiscale anuale.** Ratele, plafoanele, codurile, termenele și regulile de calcul se verifică pentru anul și categoria relevante în ANAF, Ministerul Finanțelor, Monitorul Oficial, `legislatie.just.ro` sau BNR. Literalele și exemplele din referințele bundle-uite sunt neoperative până la confirmarea lor în dovezile oficiale curente. Sursele neoficiale pot orienta căutarea, dar nu susțin concluzia.

6. **Proveniență potrivită tipului de valoare.** Parametrii legali trimit la sursa oficială și ancora din `_legi/{an}/`; sumele și datele de identificare trimit la documentul utilizatorului, inclusiv pagină, rând sau secțiune când există; rezultatele calculate arată formula și proveniența inputurilor și parametrilor. Timestamp-urile, identificatorii și metadatele sesiunii trimit la evenimentul din worklog, nu la o ancoră legală.

7. **Conversie valutară.** Pentru un calcul destinat depunerii, folosește metoda și cursul cerute de sursa oficială aplicabilă venitului și anului, cu curs BNR per dată a realizării când aceasta este regula verificată. Media anuală V2 și `cursbnr.ro` nu sunt default și nu sunt autoritate fiscală. O metodă alternativă poate apărea doar ca estimare comparativă sau ca decizie explicită susținută de dovezi oficiale; consemnează baza și diferența, iar fără suport oficial nu o folosi în D212 finală.

8. **XML și DUF.** Verificarea cu ElementTree dovedește numai că XML-ul este bine format. `outputs/D212.xml` rămâne candidat de import până când utilizatorul îl importă și îl revizuiește în DUF. Pentru depunere electronică, round-trip-ul este obligatoriu: numai re-exportul acceptat de DUF, salvat ca `outputs/D212.canonical.xml`, poate fi propus utilizatorului pentru submit. Gate-ul poate fi omis numai dacă nu se intenționează depunere electronică sau DUF este indisponibil; în al doilea caz sesiunea nu avansează la submit, iar motivul se consemnează. Consimțământul singur nu transformă XML-ul brut într-un fișier sigur pentru depunere.

## Workflow Cu Hard Gates

Citește `references/orchestrator.md` pentru detaliile fazelor, aplicând contractele canonice de mai sus:

```text
1. Identificare -> 2. Freshness schemă -> 3. Cache legi -> 4. Preflight
   -> 5. Calcul și proveniență -> 6. XML candidat și raport
   -> 6.5 DUF round-trip -> 7. Review utilizator -> 8. Închidere
```

Nu avansa silențios peste un gate. La blocaj, spune ce lipsește, ce acțiune îl rezolvă și ce rezultate nu pot fi încă produse.

## Rutare Scenariu

Citește `references/pf-investitii.md`. Pentru mai multe categorii PF, păstrează distincte inputurile, conversiile și calculele fiecărei linii de venit, apoi unifică numai obligațiile și raportul final.

## Gate-uri De Dovezi

- Refuză ratele dictate de utilizator, memoria de training, forumurile, blogurile, Reddit și știrile ca bază fiscală. Oferă verificarea concretă în sursele oficiale adecvate înainte de concluzie.
- Nu transforma estimări sau valori ținute minte în inputuri D212. Un document obligatoriu lipsă oprește preflight-ul până la furnizare sau până la un waiver explicit permis de workflow; orice waiver include motivul verbatim și timestamp în `worklog.md`.
- Nu cere și nu folosi credențiale SPV. Importul, revizuirea, re-exportul și depunerea în DUF/SPV rămân acțiuni ale utilizatorului.

## Limbă

Toată comunicarea cu utilizatorul, cache-ul, worklog-ul și raportul sunt în română. Păstrează codurile de categorie și numele atributelor XML exact ca în sursa oficială.
