# Legi cache management

Cache-ul de legi (fapte fiscale) trăiește **OUT-OF-REPO**, în:

```
/Users/trocaneduard/Documents/Personal/declaratii-unice/_legi/{an_fiscal}/
```

Asta separă date personale de skill-ul versionat și permite re-verificarea anuală fără să atingem repo-ul.

## Structură (G3 — index + module)

```
_legi/{an}/
├── README.md                          # index sintetic + last_verified per modul
├── salariu-minim.md
├── plafoane-cass.md
├── plafoane-cas.md
├── impozit-dividende.md
├── impozit-castig-capital.md
├── impozit-dobanzi.md
├── impozit-cripto.md
├── pfa-real-cheltuieli.md
├── tratate-dubla-impunere.md
├── curs-bnr-mediu.md
└── modificari-cf-fata-de-anul-precedent.md
```

Toate au frontmatter conform `workflow/citation-protocol.md`.

## README.md — index sintetic

Format:

```markdown
# Cache legi — anul fiscal {an}

| Fapt | Valoare scurtă | Modul | last_verified |
|---|---|---|---|
| Salariu minim brut | 4.050 RON | [salariu-minim.md](salariu-minim.md) | 2026-05-11 |
| Plafon CASS (12 × salariu_min) | 97.200 RON | [plafoane-cass.md](plafoane-cass.md) | 2026-05-11 |
| Cotă CASS | 10% | [plafoane-cass.md](plafoane-cass.md) | 2026-05-11 |
| Cotă impozit dividende RO | 8% | [impozit-dividende.md](impozit-dividende.md) | 2026-05-11 |
| Cotă impozit câștig capital | 10% / 1% (după caz) | [impozit-castig-capital.md](impozit-castig-capital.md) | 2026-05-11 |
| Cotă impozit dobânzi | 10% | [impozit-dobanzi.md](impozit-dobanzi.md) | 2026-05-11 |
| Curs mediu USD | 4.6612 | [curs-bnr-mediu.md](curs-bnr-mediu.md) | 2026-05-11 |
| Curs mediu EUR | 4.9745 | [curs-bnr-mediu.md](curs-bnr-mediu.md) | 2026-05-11 |

## Modificări CF față de anul precedent

Vezi [modificari-cf-fata-de-anul-precedent.md](modificari-cf-fata-de-anul-precedent.md) pentru changelog.

## Reverificare

Fiecare modul are `last_verified` în frontmatter. Trigger refresh:
- Folder lipsă pentru anul fiscal → refresh complet
- `last_verified > 90 zile` la un modul → refresh modul-by-modul
```

## Procedura de re-verificare modul

Pentru un modul stale (`last_verified > 90 zile` sau lipsă):

1. Citește `source_url` din frontmatter (sau, dacă modul nou, determină din whitelist + Instrucțiuni PDF anuale).
2. Fetch URL.
3. Extrage valoarea curentă a faptului + citat verbatim minim 1 propoziție.
4. Update frontmatter: `valoare`, `accessed_on`, `last_verified`, `citat_verbatim`.
5. Update body cu context dacă s-a schimbat.
6. Update entry în `README.md`.
7. Înregistrează în `worklog.md`:
   ```
   [YYYY-MM-DD HH:MM] legi-refresh: module=impozit-dividende.md, old_value=X%, new_value=Y%, source_url=...
   ```

## Versiunile istorice (dacă valoarea s-a schimbat semnificativ)

Dacă o reverificare descoperă schimbare materială (ex. cota dividende 5% → 8% în 2024), păstrăm istoricul:

```
_legi/2024/impozit-dividende.md         # cota 5% (anul fiscal 2024)
_legi/2025/impozit-dividende.md         # cota 8% (anul fiscal 2025)
```

Cache-ul e per-an fiscal, deci natural separat — nu folosim sufix `.v2` pe același an decât dacă există o rectificativă ANAF intra-anuală.

## Modulele relevante per scenariu

Indicat în `pf-investitii.md` și `pfa-real.md`, dar recap:

- **PF investiții**: `impozit-dividende`, `impozit-castig-capital`, `impozit-dobanzi`, `impozit-cripto`, `tratate-dubla-impunere`, `curs-bnr-mediu`, `plafoane-cass`, `salariu-minim`.
- **PFA real**: `pfa-real-cheltuieli`, `plafoane-cas`, `plafoane-cass`, `salariu-minim`, `modificari-cf-fata-de-anul-precedent`.
