"""AI-powered outreach tool that composes intelligence, behavior, and recommendations."""

from __future__ import annotations

import json
import os
import traceback

from openai import OpenAI

from app.models.customer_intelligence import HighValueCustomer
from app.models.outreach import OutreachChannelMessage, OutreachMessageResponse
from app.models.recommendation import RecommendationResponse
from app.models.transaction_analysis import TransactionAnalysisResult
from app.prompts.outreach_prompts import OUTREACH_SYSTEM_PROMPT, build_outreach_user_prompt
from app.tools.customer_tool import CustomerIntelligenceTool
from app.tools.recommendation_tool import RecommendationTool
from app.tools.transaction_tool import TransactionAnalysisTool

__all__ = ["OutreachTool"]

_DEFAULT_MODEL = "gpt-4.1-mini"


class OutreachTool:
    """Generate recommendation-aware outreach messages per customer."""

    def __init__(
        self,
        customer_tool: CustomerIntelligenceTool,
        transaction_tool: TransactionAnalysisTool,
        recommendation_tool: RecommendationTool,
    ) -> None:
        self._customer_tool = customer_tool
        self._transaction_tool = transaction_tool
        self._recommendation_tool = recommendation_tool
        self._api_key = os.getenv("OPENAI_API_KEY")
        print(
            "OutreachTool initialization: OPENAI_API_KEY is "
            + ("detected." if self._api_key else "missing.")
        )
        self._client = OpenAI(api_key=self._api_key) if self._api_key else None

    def generate_outreach_message(self, customer_id: str) -> OutreachMessageResponse:
        """Compose existing tools and return structured outreach copy."""
        customer = self._customer_tool.get_customer_profile(customer_id)
        if customer is None:
            return self._fallback_for_missing_customer(customer_id)

        analysis = self._transaction_tool.analyze_customer_transactions(customer_id)
        recommendation_response = self._recommendation_tool.generate_recommendations(customer_id)
        customer_context = self._build_customer_context(
            customer=customer,
            analysis=analysis,
            recommendation_response=recommendation_response,
        )

        generated = self._generate_with_openai(customer_context)
        if generated is None:
            return self._build_fallback_message(customer_context)

        return OutreachMessageResponse(
            customer_id=customer_id,
            personalized_email=generated["personalized_email"],
            sms_message=generated["sms_message"],
            outreach_summary=generated["outreach_summary"],
            channel_messages=[
                OutreachChannelMessage(channel="email", message=generated["personalized_email"]),
                OutreachChannelMessage(channel="sms", message=generated["sms_message"]),
            ],
        )

    def _build_customer_context(
        self,
        *,
        customer: HighValueCustomer,
        analysis: TransactionAnalysisResult,
        recommendation_response: RecommendationResponse,
    ) -> dict[str, object]:
        recommendations = [
            {
                "type": item.recommendation_type,
                "reason": item.recommendation_reason,
                "confidence_score": round(item.confidence_score, 3),
            }
            for item in recommendation_response.recommendations
        ]
        return {
            "customer_id": customer.customer_id,
            "relationship_score": customer.relationship_score,
            "income": customer.income,
            "credit_score": customer.credit_score,
            "loan_intent": customer.loan_intent,
            "spending_behavior_summary": analysis.spending_behavior_summary,
            "behavioral_indicators": analysis.behavioral_indicators.model_dump(),
            "recommendations": recommendations,
        }

    def _generate_with_openai(self, customer_context: dict[str, object]) -> dict[str, str] | None:
        if self._client is None:
            print("OutreachTool: OpenAI client unavailable because OPENAI_API_KEY is missing.")
            return None

        try:
            response = self._client.responses.create(
                model=_DEFAULT_MODEL,
                input=[
                    {"role": "system", "content": OUTREACH_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_outreach_user_prompt(customer_context=customer_context),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "outreach_message",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "personalized_email": {"type": "string"},
                                "sms_message": {"type": "string"},
                                "outreach_summary": {"type": "string"},
                            },
                            "required": [
                                "personalized_email",
                                "sms_message",
                                "outreach_summary",
                            ],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    }
                },
            )
            payload = json.loads(response.output_text)
            if not all(
                isinstance(payload.get(key), str) and payload.get(key).strip()
                for key in ("personalized_email", "sms_message", "outreach_summary")
            ):
                return None
            return {
                "personalized_email": payload["personalized_email"].strip(),
                "sms_message": payload["sms_message"].strip(),
                "outreach_summary": payload["outreach_summary"].strip(),
            }
        except Exception as exc:
            print(f"OutreachTool OpenAI generation failed: {exc}")
            traceback.print_exc()
            return None

    def _build_fallback_message(self, customer_context: dict[str, object]) -> OutreachMessageResponse:
        customer_id = str(customer_context["customer_id"])
        loan_intent = str(customer_context.get("loan_intent", "banking needs"))
        summary = str(customer_context.get("spending_behavior_summary", "")).strip()
        top_recommendation = "tailored banking solutions"
        recommendations = customer_context.get("recommendations", [])
        if recommendations:
            top_recommendation = str(recommendations[0].get("type", top_recommendation))

        email = (
            f"Dear Customer {customer_id},\n\n"
            "Thank you for banking with us. Based on your recent account activity and financial "
            f"profile, we see a strong opportunity to support your {loan_intent} goals with "
            f"our {top_recommendation} offering. {summary} "
            "Our advisors can help you compare options and choose a plan aligned with your priorities.\n\n"
            "Reply to this email or visit your branch relationship manager for a personalized discussion.\n\n"
            "Sincerely,\nYour Banking Relationship Team"
        )
        sms = (
            f"Customer {customer_id}, based on your recent activity, we can help with {top_recommendation}. "
            "Reply YES for a quick call with your relationship manager."
        )
        outreach_summary = (
            "Fallback outreach generated from customer profile, transaction behavior, and recommendation "
            "signals due to temporary AI generation unavailability."
        )
        return OutreachMessageResponse(
            customer_id=customer_id,
            personalized_email=email,
            sms_message=sms[:280],
            outreach_summary=outreach_summary,
            channel_messages=[
                OutreachChannelMessage(channel="email", message=email),
                OutreachChannelMessage(channel="sms", message=sms[:280]),
            ],
        )

    def _fallback_for_missing_customer(self, customer_id: str) -> OutreachMessageResponse:
        email = (
            f"Dear Customer {customer_id},\n\n"
            "We would like to review your current banking needs and share options that may help you "
            "achieve your financial goals. Please connect with our relationship team at your convenience.\n\n"
            "Sincerely,\nYour Banking Relationship Team"
        )
        sms = (
            f"Customer {customer_id}, our team can share personalized banking options for your goals. "
            "Reply YES to connect."
        )
        return OutreachMessageResponse(
            customer_id=customer_id,
            personalized_email=email,
            sms_message=sms[:280],
            outreach_summary="Customer profile not found; returned default outreach message.",
            channel_messages=[
                OutreachChannelMessage(channel="email", message=email),
                OutreachChannelMessage(channel="sms", message=sms[:280]),
            ],
        )
