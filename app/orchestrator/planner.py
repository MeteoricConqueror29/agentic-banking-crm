"""Agentic orchestration planner for the banking CRM workflow.

The planner is the single layer in the application allowed to coordinate the
existing ``CustomerIntelligenceTool``, ``TransactionAnalysisTool``,
``RecommendationTool``, and ``OutreachTool`` in service of one relationship
manager (RM) request. HTTP routes stay thin: they parse input, call
:meth:`Planner.run`, and serialize the structured :class:`PlannerResponse`.

Workflow
--------
1. Interpret the RM query via lightweight keyword routing into an ``_IntentPlan``
   (filters + optional recommendation focus + optional behavioral indicator).
2. Use the customer intelligence tool to retrieve candidates above thresholds.
3. For each top candidate (capped for predictable latency), run the
   transaction analysis tool.
4. Generate explainable recommendations via the recommendation tool and apply
   the intent's optional focus filter.
5. Generate personalized outreach via the outreach tool for qualifying customers.
6. Assemble one unified :class:`PlannerResponse` with orchestration metadata.

The keyword router is intentionally simple and easy to extend: each rule maps a
canonical intent name to (keywords, plan factory). First match wins so the
behavior stays predictable and deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.customer_intelligence import HighValueCustomerFilters
from app.models.planner import (
    CustomerOrchestrationResult,
    InterpretedIntent,
    OrchestrationStep,
    OrchestrationSummary,
    PlannerResponse,
)
from app.models.recommendation import CustomerRecommendation
from app.models.transaction_analysis import TransactionAnalysisResult
from app.tools.customer_tool import CustomerIntelligenceTool
from app.tools.outreach_tool import OutreachTool
from app.tools.recommendation_tool import RecommendationTool
from app.tools.transaction_tool import TransactionAnalysisTool

__all__ = ["Planner"]

_DEFAULT_MAX_CUSTOMERS = 5


@dataclass(frozen=True)
class _IntentPlan:
    """Internal routing decision produced by the keyword interpreter."""

    name: str
    description: str
    filters: HighValueCustomerFilters
    focus_recommendation_type: str | None = None
    required_indicator: str | None = None
    matched_keywords: tuple[str, ...] = ()


def _intent_investment_products(matched: tuple[str, ...]) -> _IntentPlan:
    return _IntentPlan(
        name="investment_products",
        description=(
            "Match affluent, credit-worthy customers most suitable for investment products."
        ),
        filters=HighValueCustomerFilters(
            min_relationship_score=70.0,
            min_income=80_000.0,
            min_credit_score=720,
        ),
        focus_recommendation_type="investment products",
        matched_keywords=matched,
    )


def _intent_premium_credit_card(matched: tuple[str, ...]) -> _IntentPlan:
    return _IntentPlan(
        name="premium_credit_card",
        description=(
            "Identify premium credit card candidates with strong credit and elevated spending activity."
        ),
        filters=HighValueCustomerFilters(
            min_relationship_score=65.0,
            min_income=60_000.0,
            min_credit_score=700,
        ),
        focus_recommendation_type="premium credit card",
        required_indicator="high_spending_activity",
        matched_keywords=matched,
    )


def _intent_travel_rewards_card(matched: tuple[str, ...]) -> _IntentPlan:
    return _IntentPlan(
        name="travel_rewards_card",
        description="Surface travel-heavy spenders well suited to a travel rewards card.",
        filters=HighValueCustomerFilters(
            min_relationship_score=55.0,
            min_income=45_000.0,
            min_credit_score=660,
        ),
        focus_recommendation_type="travel rewards card",
        required_indicator="travel_heavy_customer",
        matched_keywords=matched,
    )


def _intent_personal_loan(matched: tuple[str, ...]) -> _IntentPlan:
    return _IntentPlan(
        name="personal_loan_offers",
        description="Find customers whose credit profile and intent fit personal loan offers.",
        filters=HighValueCustomerFilters(
            min_relationship_score=45.0,
            min_income=35_000.0,
            min_credit_score=620,
        ),
        focus_recommendation_type="personal loan offers",
        matched_keywords=matched,
    )


def _intent_savings_upgrade(matched: tuple[str, ...]) -> _IntentPlan:
    return _IntentPlan(
        name="savings_account_upgrades",
        description="Surface utility-focused, engaged customers for savings account upgrades.",
        filters=HighValueCustomerFilters(
            min_relationship_score=50.0,
            min_income=30_000.0,
            min_credit_score=640,
        ),
        focus_recommendation_type="savings account upgrades",
        required_indicator="utility_focused_customer",
        matched_keywords=matched,
    )


def _intent_high_value_default(matched: tuple[str, ...]) -> _IntentPlan:
    return _IntentPlan(
        name="high_value_customers",
        description=(
            "Default plan: rank generally high-value customers and present the full recommendation mix."
        ),
        filters=HighValueCustomerFilters(
            min_relationship_score=60.0,
            min_income=50_000.0,
            min_credit_score=700,
        ),
        focus_recommendation_type=None,
        matched_keywords=matched,
    )


# Ordered keyword rules. First rule whose keywords appear in the query wins, keeping
# the router deterministic and trivial to extend (add a row, ship a new intent).
_KEYWORD_RULES: tuple[
    tuple[tuple[str, ...], Callable[[tuple[str, ...]], _IntentPlan]],
    ...,
] = (
    (
        ("investment", "invest", "wealth", "portfolio", "mutual fund"),
        _intent_investment_products,
    ),
    (
        ("travel", "vacation", "trip", "flight"),
        _intent_travel_rewards_card,
    ),
    (
        ("premium", "platinum", "elite credit", "premium card"),
        _intent_premium_credit_card,
    ),
    (
        ("personal loan", "loan", "lending", "borrow"),
        _intent_personal_loan,
    ),
    (
        ("savings", "deposit", "saver", "high-yield"),
        _intent_savings_upgrade,
    ),
)


class Planner:
    """Coordinate the four CRM tools into one explainable, structured workflow.

    The planner accepts an RM query, interprets intent, retrieves customers,
    enriches each with transaction insights, recommendations, and outreach,
    and returns a single :class:`PlannerResponse`.

    Notes:
        - This is the only layer permitted to call multiple tools together.
        - Tools are reused as-is; no business logic is duplicated here.
        - Per-customer processing is capped (``max_customers``) for predictable
          response times, since outreach generation can be I/O heavy.
    """

    def __init__(
        self,
        customer_tool: CustomerIntelligenceTool,
        transaction_tool: TransactionAnalysisTool,
        recommendation_tool: RecommendationTool,
        outreach_tool: OutreachTool,
        *,
        max_customers: int = _DEFAULT_MAX_CUSTOMERS,
    ) -> None:
        self._customer_tool = customer_tool
        self._transaction_tool = transaction_tool
        self._recommendation_tool = recommendation_tool
        self._outreach_tool = outreach_tool
        self._max_customers = max(1, int(max_customers))

    def run(
        self,
        query: str,
        *,
        generate_outreach: bool = True,
        max_customers: int | None = None,
    ) -> PlannerResponse:
        """Execute the full planner workflow for an RM ``query``.

        Args:
            query: Free-form relationship-manager request.
            generate_outreach: When ``False``, skip the outreach tool (faster).
            max_customers: Optional override for the per-call cap on customers
                processed in detail. ``None`` uses the planner default.

        Returns:
            A :class:`PlannerResponse` with interpreted intent, per-customer
            enrichment, and orchestration metadata.
        """
        cleaned_query = (query or "").strip()
        cap = max(1, int(max_customers)) if max_customers is not None else self._max_customers
        steps: list[OrchestrationStep] = []

        # Step 1 — Interpret intent from the RM query.
        plan = self._interpret_intent(cleaned_query)
        steps.append(
            OrchestrationStep(
                name="interpret_intent",
                detail=(
                    f"Routed to '{plan.name}' via keywords: "
                    f"{', '.join(plan.matched_keywords) or 'default (no keywords matched)'}"
                ),
            )
        )

        # Step 2 — Retrieve customers via the customer intelligence tool.
        query_result = self._customer_tool.find_high_value_customers(plan.filters)
        candidates = query_result.customers
        steps.append(
            OrchestrationStep(
                name="retrieve_customers",
                detail=f"{len(candidates)} candidate(s) above filter thresholds.",
            )
        )

        # Steps 3-5 — Per-customer enrichment (transactions → recommendations → outreach).
        per_customer_results = self._enrich_customers(
            candidates=candidates,
            plan=plan,
            generate_outreach=generate_outreach,
            cap=cap,
        )

        steps.append(
            OrchestrationStep(
                name="analyze_transactions",
                detail=f"Analyzed transactions for {len(per_customer_results)} customer(s).",
            )
        )
        steps.append(
            OrchestrationStep(
                name="generate_recommendations",
                detail=(
                    f"Recommendation focus: "
                    f"{plan.focus_recommendation_type or 'mixed (full recommendation set)'}."
                ),
            )
        )
        steps.append(
            OrchestrationStep(
                name="generate_outreach",
                status="completed" if generate_outreach else "skipped",
                detail=(
                    "Outreach messages generated per qualified customer."
                    if generate_outreach
                    else "Outreach generation skipped by caller."
                ),
            )
        )

        # Step 6 — Assemble unified response.
        intent = InterpretedIntent(
            name=plan.name,
            description=plan.description,
            matched_keywords=list(plan.matched_keywords),
            focus_recommendation_type=plan.focus_recommendation_type,
            required_behavioral_indicator=plan.required_indicator,
        )

        summary = OrchestrationSummary(
            query=cleaned_query,
            interpreted_intent=intent,
            candidates_retrieved=len(candidates),
            customers_processed=len(per_customer_results),
            recommendations_generated=sum(len(r.recommendations) for r in per_customer_results),
            outreach_messages_generated=sum(
                1 for r in per_customer_results if r.outreach is not None
            ),
            steps=steps,
            generated_at=datetime.now(timezone.utc),
        )

        return PlannerResponse(
            query=cleaned_query,
            interpreted_intent=intent,
            matched_customers=per_customer_results,
            orchestration_summary=summary,
        )

    # ---------------------------------------------------------------------- #
    # Internal pipeline helpers                                              #
    # ---------------------------------------------------------------------- #

    def _interpret_intent(self, query: str) -> _IntentPlan:
        """Lightweight keyword router; falls back to the default high-value plan."""
        if not query:
            return _intent_high_value_default(())
        lowered = query.lower()
        for keywords, factory in _KEYWORD_RULES:
            matched = tuple(kw for kw in keywords if kw in lowered)
            if matched:
                return factory(matched)
        return _intent_high_value_default(())

    def _enrich_customers(
        self,
        *,
        candidates: list,
        plan: _IntentPlan,
        generate_outreach: bool,
        cap: int,
    ) -> list[CustomerOrchestrationResult]:
        """Run per-customer tools and apply intent-driven filters."""
        enriched: list[CustomerOrchestrationResult] = []
        for customer in candidates:
            if len(enriched) >= cap:
                break

            analysis = self._transaction_tool.analyze_customer_transactions(customer.customer_id)
            if not self._customer_matches_indicator(analysis, plan.required_indicator):
                continue

            recommendations = self._collect_recommendations(
                customer.customer_id,
                plan.focus_recommendation_type,
            )
            # If the intent has a focused recommendation type and the tool produced
            # no confident match for it, the customer is not a fit — skip them.
            if plan.focus_recommendation_type and not recommendations:
                continue

            outreach = (
                self._outreach_tool.generate_outreach_message(customer.customer_id)
                if generate_outreach
                else None
            )

            enriched.append(
                CustomerOrchestrationResult(
                    customer=customer,
                    transaction_analysis=analysis,
                    recommendations=recommendations,
                    outreach=outreach,
                )
            )
        return enriched

    def _collect_recommendations(
        self,
        customer_id: str,
        focus_recommendation_type: str | None,
    ) -> list[CustomerRecommendation]:
        """Delegate to the recommendation tool and optionally narrow to the intent focus."""
        response = self._recommendation_tool.generate_recommendations(customer_id)
        if focus_recommendation_type is None:
            return list(response.recommendations)
        focus = focus_recommendation_type.lower()
        return [
            rec for rec in response.recommendations
            if rec.recommendation_type.lower() == focus
        ]

    @staticmethod
    def _customer_matches_indicator(
        analysis: TransactionAnalysisResult,
        required_indicator: str | None,
    ) -> bool:
        """Return ``True`` when the analysis satisfies the optional behavioral filter."""
        if not required_indicator:
            return True
        return bool(getattr(analysis.behavioral_indicators, required_indicator, False))
