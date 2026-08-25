"""AI Sales Brief Generator.

Turns a government event + company profile + opportunity + score + contact +
evidence into a concise, sales-ready brief that strictly distinguishes verified
facts from inferred reasoning. It never invents contract details, company facts,
contact information, business needs or dates: the fact-bearing sections are built
deterministically from a grounded FactBook, and any optional LLM prose is
verified against that FactBook — unsupported claims are flagged and replaced.
"""
from __future__ import annotations

from app.brief.generator import SalesBriefGenerator
from app.brief.types import BriefInput, ContactInfo, Fact, SalesBrief, Section

__all__ = ["SalesBriefGenerator", "BriefInput", "ContactInfo", "SalesBrief", "Section", "Fact"]
