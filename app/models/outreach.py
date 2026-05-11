"""Structured payloads for AI-powered customer outreach messages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OutreachChannelMessage(BaseModel):
    """One channel-specific outreach message."""

    model_config = ConfigDict(frozen=True)

    channel: str = Field(..., description="Delivery channel, such as 'email' or 'sms'.")
    message: str = Field(..., min_length=1, description="Generated outreach copy for the channel.")


class OutreachMessageResponse(BaseModel):
    """Stable response shape for personalized customer outreach."""

    model_config = ConfigDict(extra="ignore")

    customer_id: str
    personalized_email: str = Field(..., min_length=1)
    sms_message: str = Field(..., min_length=1)
    outreach_summary: str = Field(..., min_length=1)
    channel_messages: list[OutreachChannelMessage] = Field(
        default_factory=list,
        description="Optional normalized channel mapping for downstream systems.",
    )
