"""Recommendation tool that combines customer intelligence and spending behavior."""

from __future__ import annotations

from app.models.customer_intelligence import HighValueCustomer
from app.models.recommendation import CustomerRecommendation, RecommendationResponse
from app.models.transaction_analysis import TransactionAnalysisResult
from app.tools.customer_tool import CustomerIntelligenceTool
from app.tools.transaction_tool import TransactionAnalysisTool

__all__ = ["RecommendationTool"]

_MIN_CONFIDENCE_THRESHOLD = 0.55


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _credit_component(score: int, floor: int, ceiling: int) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp01((score - floor) / (ceiling - floor))


def _relationship_component(score: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp01((score - floor) / (ceiling - floor))


def _category_share_map(analysis: TransactionAnalysisResult) -> dict[str, float]:
    return {
        category.transaction_type.lower(): category.share_of_spend
        for category in analysis.category_breakdown
    }


class RecommendationTool:
    """Generate explainable, per-customer banking recommendations."""

    def __init__(
        self,
        customer_tool: CustomerIntelligenceTool,
        transaction_tool: TransactionAnalysisTool,
    ) -> None:
        self._customer_tool = customer_tool
        self._transaction_tool = transaction_tool

    def generate_recommendations(self, customer_id: str) -> RecommendationResponse:
        """Compose existing tools and return ranked recommendations."""
        customer = self._customer_tool.get_customer_profile(customer_id)
        if customer is None:
            return RecommendationResponse(customer_id=customer_id, recommendations=[])

        analysis = self._transaction_tool.analyze_customer_transactions(customer_id)
        candidates = [
            self._premium_credit_card(customer, analysis),
            self._travel_rewards_card(customer, analysis),
            self._investment_products(customer, analysis),
            self._personal_loan_offers(customer, analysis),
            self._savings_account_upgrades(customer, analysis),
        ]
        filtered = [c for c in candidates if c and c.confidence_score >= _MIN_CONFIDENCE_THRESHOLD]
        filtered.sort(key=lambda item: item.confidence_score, reverse=True)
        return RecommendationResponse(customer_id=customer_id, recommendations=filtered)

    def _premium_credit_card(
        self,
        customer: HighValueCustomer,
        analysis: TransactionAnalysisResult,
    ) -> CustomerRecommendation:
        relationship = _relationship_component(customer.relationship_score, 60.0, 90.0)
        credit = _credit_component(customer.credit_score, 680, 820)
        spend_signal = 1.0 if analysis.behavioral_indicators.high_spending_activity else 0.45
        confidence = _clamp01(0.40 * relationship + 0.40 * credit + 0.20 * spend_signal)
        reason = (
            f"Strong relationship score ({customer.relationship_score:.1f}) and credit score "
            f"({customer.credit_score}) with elevated spending activity support a premium card offer."
        )
        return CustomerRecommendation(
            recommendation_type="premium credit card",
            recommendation_reason=reason,
            confidence_score=confidence,
        )

    def _travel_rewards_card(
        self,
        customer: HighValueCustomer,
        analysis: TransactionAnalysisResult,
    ) -> CustomerRecommendation:
        shares = _category_share_map(analysis)
        travel_share = shares.get("travel", 0.0)
        travel_indicator = 1.0 if analysis.behavioral_indicators.travel_heavy_customer else 0.55
        credit = _credit_component(customer.credit_score, 640, 790)
        relationship = _relationship_component(customer.relationship_score, 50.0, 85.0)
        confidence = _clamp01(
            0.45 * max(travel_share, travel_indicator * 0.8)
            + 0.35 * credit
            + 0.20 * relationship
        )
        reason = (
            f"Travel spend concentration ({travel_share * 100:.1f}% of total) and solid credit "
            f"({customer.credit_score}) indicate fit for a travel rewards card."
        )
        return CustomerRecommendation(
            recommendation_type="travel rewards card",
            recommendation_reason=reason,
            confidence_score=confidence,
        )

    def _investment_products(
        self,
        customer: HighValueCustomer,
        analysis: TransactionAnalysisResult,
    ) -> CustomerRecommendation:
        relationship = _relationship_component(customer.relationship_score, 60.0, 90.0)
        credit = _credit_component(customer.credit_score, 670, 820)
        income_signal = _clamp01(customer.income / 150000.0)
        confidence = _clamp01(0.35 * relationship + 0.30 * credit + 0.35 * income_signal)
        reason = (
            f"High relationship strength ({customer.relationship_score:.1f}), credit profile "
            f"({customer.credit_score}), and income (${customer.income:,.0f}) suggest investment suitability."
        )
        return CustomerRecommendation(
            recommendation_type="investment products",
            recommendation_reason=reason,
            confidence_score=confidence,
        )

    def _personal_loan_offers(
        self,
        customer: HighValueCustomer,
        analysis: TransactionAnalysisResult,
    ) -> CustomerRecommendation:
        loan_intent_signal = 1.0 if customer.loan_intent and customer.loan_intent.lower() != "none" else 0.45
        relationship = _relationship_component(customer.relationship_score, 45.0, 80.0)
        credit = _credit_component(customer.credit_score, 600, 760)
        utility_signal = 1.0 if analysis.behavioral_indicators.utility_focused_customer else 0.55
        confidence = _clamp01(
            0.30 * loan_intent_signal + 0.30 * credit + 0.20 * relationship + 0.20 * utility_signal
        )
        reason = (
            f"Loan intent '{customer.loan_intent}' with credit score {customer.credit_score} and "
            "stable behavior indicators supports a personal loan offer."
        )
        return CustomerRecommendation(
            recommendation_type="personal loan offers",
            recommendation_reason=reason,
            confidence_score=confidence,
        )

    def _savings_account_upgrades(
        self,
        customer: HighValueCustomer,
        analysis: TransactionAnalysisResult,
    ) -> CustomerRecommendation:
        relationship = _relationship_component(customer.relationship_score, 50.0, 85.0)
        utility_signal = 1.0 if analysis.behavioral_indicators.utility_focused_customer else 0.60
        volume_signal = _clamp01(analysis.total_transactions / 35.0)
        confidence = _clamp01(0.35 * relationship + 0.35 * utility_signal + 0.30 * volume_signal)
        reason = (
            f"Relationship score ({customer.relationship_score:.1f}) and recurring essentials-driven spending "
            "support an upgraded savings account proposition."
        )
        return CustomerRecommendation(
            recommendation_type="savings account upgrades",
            recommendation_reason=reason,
            confidence_score=confidence,
        )
