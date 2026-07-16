# Citation protocol

Disciplina de citare pentru orice fapt fiscal folosit în calcul.

## Whitelist surse (recap din spec)

**Primare (citare directă acceptată):**
- `anaf.ro` — inclusiv `/declaratii/duf`, `/declaratii_R/*`, Instrucțiuni PDF, Broșură PDF, comunicate
- `mfinante.gov.ro` / `mfp.gov.ro`
- `monitoruloficial.ro`
- `legislatie.just.ro`
- `bnr.ro`

**Secundare (navigare/index, nu citare):**
- `static.anaf.ro`
- `cdep.ro`
- `cursbnr.ro` — convenience pentru media anuală V2

**Refuzate:**
- Reddit, Avocatnet, GoldRing, contzilla, forumuri
- Profit.ro, HotNews, Capital.ro, Ziarul Financiar, alte știri
- Bloguri contabili individuali, agregatoare neoficiale
- Memoria din training a agentului

## Format frontmatter pe modulele cache

Fiecare fișier din `_legi/{an}/*.md` (cu excepția README.md) începe cu:

```yaml
---
fapt: <nume_fapt_unic>           # ex. cota_impozit_dividende
valoare: <valoarea numerică sau string scurt>
articol: <articol legal>          # ex. "Codul Fiscal art. 97 alin. (7)"
source_url: <URL whitelist>
source_type: <pdf-oficial | pagina-oficiala | monitor-oficial>
accessed_on: <YYYY-MM-DD>
last_verified: <YYYY-MM-DD>
citat_verbatim: |
  <citat ≥ 1 propoziție, păstrat exact ca în sursă>
---
```

Body-ul (după frontmatter) conține:
- **Ancore markdown** (`# Cota`, `# Plafon`, etc.) la care fac referință cache_ref din `form-mapping.yaml`
- **Context** (de ce e relevant)
- **Exemple** dacă ajută

## Format citare în worklog și raport

Pentru fiecare valoare numerică, ancoră inline `[descriere: cache_path#anchor]`:

```
câștig capital total cap 2012: 13.105 RON
  [cota 10%: _legi/2025/impozit-castig-capital.md#cota-art-94]
  [agregare anuală FIFO: _legi/2025/impozit-castig-capital.md#regula-anuala-broker-international]
  [conversie V2 USD→RON: _legi/2025/curs-bnr-mediu.md (USD=4.6612)]
  [V2 advisory: _legi/2025/curs-bnr-mediu.md#avertisment-vs-per-tranzactie]
```

## Anti-halucinare

Agentul aplică următoarele reguli:

1. **Nu folosi cunoștințe din training** ca sursă autoritativă, niciodată. Cunoștințele din training sunt utile pentru navigare ("știu unde să caut") dar NU pentru citare ("articolul X spune Y").

2. **Lipsește un fapt** → trei pași:
   a. Caută în `_legi/{an}/`
   b. Lipsește acolo → fetch din whitelist (anaf.ro Instrucțiuni PDF, legislatie.just.ro Codul Fiscal, monitoruloficial.ro pentru OUG-uri/ordine)
   c. Whitelist nu acoperă → întreabă user

3. **User citează sursă refuzată** (Reddit, blog, etc.) → agent refuză:
   ```
   Sursa X (Reddit/blog/știre) nu e acceptată ca sursă autoritativă conform
   whitelist-ului. Pot să verific aceeași afirmație din [sursa primară
   relevantă, ex. Codul Fiscal art. Y]?
   ```

4. **User cere skip citation** ("știi tu, hai mai repede") → agent refuză:
   ```
   Skill-ul cere citare pentru fiecare valoare numerică, ca audit trail.
   Continui cu citarea — durează ~30 secunde să fetch din cache. Dacă
   cache-ul lipsește, intru în re-verificare scurtă.
   ```

## Loguri

Fiecare fetch nou (sau re-fetch) se înregistrează în `worklog.md`:

```
[YYYY-MM-DD HH:MM] fetch: source_url=<URL>, fapt=<nume>, status=<200|404|...>, cached_to=<path>
```
