# known-defects fixture

A small invented lending project. Each row below is a defect seeded on purpose; `arch check` run with no base
must report exactly this set. The tests read this table as the expected set, so edit it together with the fixture.

Several seeds meet in one finding when they share a target and a defect kind (a finding lists every rule it breaks),
and some seeds also trip a neighbouring check on a different target. Both are listed.

| Target | Check | Rules | Defect |
|---|---|---|---|
| `src/lending/renewal-use-case.ts -> src/storage/audit-log.ts` | `policy-imports-detail` | R4 | `policy-depends-on-detail` |
| `src/lending/loan-use-case.ts -> src/storage/sql-loan-store.ts` | `policy-imports-detail` | R4 | `policy-depends-on-detail` |
| `src/lending/loan-use-case.ts -> src/storage/sql-loan-store.ts` | `policy-detail-edge-beside-port` | R5 | `policy-depends-on-detail` |
| `src/lending/loan-store.ts -> src/storage/sql-row.ts` | `policy-imports-detail` | R4 | `policy-depends-on-detail` |
| `src/lending/loan-store.ts -> src/storage/sql-row.ts` | `port-signature-detail-type` | R5 | `port-carries-detail-type` |
| `src/lending/loan-use-case.ts -> external:pg` | `policy-imports-external` | R4 | `policy-depends-on-detail` |
| `src/lending/member.ts -> external:orm` | `policy-imports-external` | R4 | `policy-depends-on-detail` |
| `src/lending/member.ts -> external:orm` | `entity-imports-non-entity` | R17 | `policy-depends-on-detail` |
| `src/lending/overdue-fee.ts -> src/lending/loan-store.ts` | `entity-imports-non-entity` | R17 | `entity-depends-outward` |
| `src/lending/reservation.ts -> src/lending/renewal-use-case.ts` | `entity-imports-non-entity` | R17 | `entity-depends-outward` |
| `src/lending/reservation.ts -> src/lending/renewal-use-case.ts` | `entity-imports-use-case` | R18 | `entity-depends-outward` |
| `src/lending/reservation.ts -> src/lending/renewal-use-case.ts` | `outward-ring-edge` | R4 | `outward-dependency` |
| `src/lending/renewal-use-case.ts -> src/notify/notifier.ts` | `outward-ring-edge` | R4 | `outward-dependency` |
| `src/lending/renewal-use-case.ts -> src/notify/notifier.ts` | `port-owner-below-consumer` | R5 | `port-on-wrong-side` |
| `src/lending/loan-request.ts -> src/lending/loan.ts` | `boundary-data-imports` | R19 | `boundary-data-not-plain` |
| `src/web/loan-presenter.ts -> src/web/ui-shell.ts` | `outward-ring-edge` | R4 | `outward-dependency` |
| `src/web/loan-presenter.ts -> external:react` | `presenter-imports-ui-framework` | R21 | `presenter-bound-to-framework` |
| `src/web/loan-presenter.ts -> src/notify/mail-notifier.ts` | `forbidden-edge-present` | R39 | `forbidden-edge` |
| `src/web/loan-controller.ts -> src/lending/loan-use-case.ts` | `controller-imports-use-case` | R6 | `use-case-called-without-boundary` |
| `src/web/loan-controller.ts -> src/storage/sql-loan-store.ts` | `detail-constructed-outside-root` | R7 | `detail-constructed-outside-root` |
| `src/web/loan-controller.ts -> src/storage/sql-loan-store.ts` | `type-check-on-implementation` | R13 | `consumer-checks-implementation` |
| `src/web/catalog-page.ts -> src/catalog/internal/index-builder.ts` | `deep-import` | R38 | `deep-import` |
| `src/catalog/api/search.ts#SuggestionSource` | `unconsumed-export` | R38 | `published-without-consumer` |
| `src/storage/sql-loan-store.ts -> src/notify/mail-notifier.ts` | `plugin-imports-plugin` | R25 | `plugins-coupled` |
| `src/storage/sql-loan-store.ts -> src/storage/loan-store.test.ts` | `production-imports-test` | R34 | `production-depends-on-test` |
| `notify` | `unenforced-component` | R38 | `boundary-not-enforced` |
| `web -> reports` | `thin-component-use` | R27 | `thin-component-use` |
| `reports` | `distance-over-threshold` | R32 | `off-balance` |
| `lending -> notify -> storage` | `component-cycle` | R30 | `cycle` |
| `src/lending/penalty.ts -> src/lending/waiver.ts` | `module-cycle` | R30 | `cycle` |
| `storage -> lending` | `unstable-dependency` | R31 | `depends-on-less-stable` |
| `storage -> notify` | `unstable-dependency` | R31 | `depends-on-less-stable` |
| `archive` | `unused-abstractions` | R31, R32 | `unused-abstraction` |

Findings that merge into one row: `member.ts -> external:orm` (R4 and R17), `loan-use-case.ts -> sql-loan-store.ts`
(R4 and R5), and `reservation.ts -> renewal-use-case.ts` under `entity-depends-outward` (R17 and R18).

Not seeded, because they need a base to compare against: `zone-of-pain`, `no-cohesion-groups`, `change-spans-groups`.
The classification and exports of every module are known, so nothing is reported as incomplete.
