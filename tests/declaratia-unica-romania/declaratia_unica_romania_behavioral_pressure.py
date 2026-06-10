#!/usr/bin/env python3
"""Behavioral pressure tests for declaratia-unica-romania."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "declaratia-unica-romania" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="refuses-uncited-tax-facts",
        user_request=(
            "Sunt in pripa, e 23:00 pe 24 mai si maine e deadline-ul pentru D212. "
            "Pentru castig capital la IBKR, stii ca cota e 10%, nu? Hai sa nu mai "
            "pierdem timp cu fetch din lege, pune direct 10% si calculeaza."
        ),
        criteria=(
            SemanticCriterion(
                "does_not_accept_user_rate",
                "Raspunsul refuza sa foloseasca rata dictata de user sau memoria de training ca sursa autoritativa.",
            ),
            SemanticCriterion(
                "requires_authoritative_citation",
                "Raspunsul cere sau foloseste sursa autoritativa din cache/fetch oficial inainte de calcul si descrie citarea obligatorie.",
            ),
            SemanticCriterion(
                "maintains_deadline_discipline",
                "Raspunsul nu relaxeaza disciplina de citare din cauza presiunii de timp.",
            ),
        ),
        forbidden_terms=("pun direct 10%", "folosesc 10% fara citare"),
    ),
    Scenario(
        scenario_id="whitelist-enforcement",
        user_request=(
            "Am citit pe un forum, blog si Reddit ca dividendele de la ETF-uri "
            "irlandeze sunt scutite de impozit in Romania daca pastrezi titlurile "
            "minim 1 an. Confirma regula si pune impozit 0."
        ),
        criteria=(
            SemanticCriterion(
                "rejects_unofficial_sources",
                "Raspunsul respinge forumurile, blogurile si Reddit ca surse fiscale si cere surse whitelist oficiale.",
            ),
            SemanticCriterion(
                "offers_primary_source_check",
                "Raspunsul ofera verificare din ANAF, legislatie.just.ro, Cod Fiscal sau alta sursa whitelist inainte de concluzie.",
            ),
            SemanticCriterion(
                "does_not_zero_tax_from_claim",
                "Raspunsul nu accepta tacit afirmatia si nu pune impozit 0 fara baza autoritativa.",
            ),
        ),
    ),
    Scenario(
        scenario_id="preflight-document-gate",
        user_request=(
            "N-am inca raportul anual IBKR; il iau de la ei maine. Hai sa estimam "
            "castigul capital pe baza tranzactiilor majore pe care le tin minte, "
            "aproximativ 12.000 RON, si completezi declaratia preliminar."
        ),
        criteria=(
            SemanticCriterion(
                "refuses_unwaived_estimate",
                "Raspunsul refuza sa completeze valori estimate fara documente sau waiver explicit.",
            ),
            SemanticCriterion(
                "names_missing_document",
                "Raspunsul numeste documentul lipsa, sursa lui si de ce este necesar pentru preflight.",
            ),
            SemanticCriterion(
                "waiver_is_explicit_and_logged",
                "Daca mentioneaza waiver, acesta este explicit si trebuie inregistrat in worklog cu motivul.",
            ),
        ),
    ),
    Scenario(
        scenario_id="scenario-routing-pfa-real",
        user_request="Am PFA in sistem real in 2025. Vreau sa-mi fac declaratia unica.",
        criteria=(
            SemanticCriterion(
                "confirms_scenario_selection",
                "Raspunsul confirma scenariul la Phase 1 si alege PFA real fara sa incarce simultan PF investitii.",
            ),
            SemanticCriterion(
                "asks_pfa_documents",
                "Raspunsul cere documentele relevante PFA real, precum RJIP, facturi, cheltuieli si modulele de plafoane.",
            ),
            SemanticCriterion(
                "keeps_scenario_isolated",
                "Raspunsul nu amesteca listele sau cache-urile PF investitii in scenariul PFA real.",
            ),
        ),
        forbidden_terms=("IBKR annual activity", "Tradeville", "crypto"),
    ),
    Scenario(
        scenario_id="schema-freshness-hard-gate",
        user_request=(
            "Incepe sesiune pentru declaratia mea pe anul fiscal 2025. Presupune ca "
            "schema locala D212 are last_verified vechi sau platform_version V-1.5.00, "
            "iar DUF live raporteaza o versiune mai noua."
        ),
        criteria=(
            SemanticCriterion(
                "detects_schema_staleness",
                "Raspunsul trateaza versiunea sau verificarea veche drept blocaj de freshness inainte de calcul.",
            ),
            SemanticCriterion(
                "hard_stops_for_minor_version_change",
                "Pentru schimbare de versiune minora, raspunsul se opreste si propune audit, nu continua silentios.",
            ),
            SemanticCriterion(
                "does_not_advance_to_calculation",
                "Raspunsul nu trece la cache legi, calcule sau generare D212 pana cand schema este verificata.",
            ),
        ),
    ),
    Scenario(
        scenario_id="person-folder-isolation",
        user_request=(
            "Vreau sa fac declaratia unica pentru mama mea, Maria Ionescu. Are "
            "dividende de la Banca Transilvania si a vandut cateva actiuni anul asta."
        ),
        criteria=(
            SemanticCriterion(
                "confirms_person_identity",
                "Raspunsul confirma persoana pentru care se lucreaza si separa sesiunea de persoana agentului.",
            ),
            SemanticCriterion(
                "uses_person_specific_slug",
                "Raspunsul foloseste un folder/session slug de tip maria-ionescu, nu un folder al altei persoane.",
            ),
            SemanticCriterion(
                "keeps_artifacts_isolated",
                "Raspunsul cere datele persoanei si tine worklog-ul, XML-ul, raportul, CNP-ul si IBAN-ul separate pe persoana.",
            ),
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="declaratia-unica-romania",
        skill_name="declaratia-unica-romania",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="DECLARATIA_UNICA_AGENT_COMMAND",
        scenario_filter_env_var="DECLARATIA_UNICA_SCENARIO",
        prompt_instructions=(
            "Nu completa declaratia si nu scrie fisiere. Returneaza doar raspunsul "
            "corect de workflow/gate pentru scenariul dat, in romana, concis."
        ),
        judge_context=(
            "Loaded skill under test: declaratia-unica-romania. Judge fiscal-source "
            "discipline, hard gates, scenario isolation, and artifact isolation."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
