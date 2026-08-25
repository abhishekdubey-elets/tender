"""Opportunity Detection Engine.

Given a government event + company profile + customer target profile + customer
products, it determines what business needs the event could create — as
*hypotheses*, never facts. Deterministic rules (driven by a configurable Product
Opportunity Knowledge Base) run first; an optional injected LLM reasoner refines
the narrative without adding facts.

Every opportunity carries its epistemic tier (FACT / INFERENCE / SPECULATION),
trigger, reasoning, supporting evidence, confidence, timing, assumptions and
alternative explanations.
"""
from __future__ import annotations

from app.opportunity.engine import OpportunityEngine
from app.opportunity.knowledge_base import (
    BusinessNeed,
    KnowledgeBase,
    ProductRule,
    default_knowledge_base,
)
from app.opportunity.types import (
    CompanyProfileInput,
    EpistemicTier,
    EventInput,
    Evidence,
    Opportunity,
    OpportunityBundle,
    ProductInput,
    SignalInfo,
    TargetProfile,
)

__all__ = [
    "OpportunityEngine",
    "KnowledgeBase",
    "ProductRule",
    "BusinessNeed",
    "default_knowledge_base",
    "EventInput",
    "CompanyProfileInput",
    "TargetProfile",
    "ProductInput",
    "SignalInfo",
    "Opportunity",
    "OpportunityBundle",
    "Evidence",
    "EpistemicTier",
]
