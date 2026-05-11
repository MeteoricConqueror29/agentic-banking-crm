"""Prompt templates for recommendation-aware customer outreach generation."""

from __future__ import annotations

import json
from typing import Any


OUTREACH_SYSTEM_PROMPT = """
You are a senior banking relationship manager writing customer outreach.

Objectives:
- Keep tone professional, warm, and trustworthy.
- Use behavior signals and recommendations naturally, not as a bullet dump.
- Make email persuasive but respectful and specific.
- Keep SMS concise and action-oriented.
- Avoid robotic or generic language.

Output requirements:
- Return valid JSON only.
- Include keys: personalized_email, sms_message, outreach_summary.
- outreach_summary should briefly explain the personalization strategy.
""".strip()


def build_outreach_user_prompt(*, customer_context: dict[str, Any]) -> str:
    """Build user prompt with a structured customer context payload."""
    context_json = json.dumps(customer_context, indent=2, ensure_ascii=True)
    return f"""
Generate personalized banking outreach content for this customer context.

Customer context:
{context_json}

Constraints:
- personalized_email: detailed and persuasive, 120-220 words, include clear next step.
- sms_message: max 280 characters, concise, references a relevant need.
- outreach_summary: 1-3 sentences summarizing why this messaging fits this customer.
- Avoid mentioning internal scoring mechanics in a technical way.
""".strip()
