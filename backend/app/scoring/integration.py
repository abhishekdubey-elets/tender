"""Bridge: build a ScoringInput from opportunity-engine outputs (pure)."""
from __future__ import annotations

from collections.abc import Callable

from app.opportunity.types import (
    CompanyProfileInput,
    EventInput,
    Opportunity,
    TargetProfile,
)
from app.scoring.types import ScoringInput


def scoring_input_from_opportunity(
    *,
    event: EventInput,
    company: CompanyProfileInput,
    target: TargetProfile,
    opportunity: Opportunity,
    num_contacts: int = 0,
    best_contact_seniority: str | None = None,
    ideal_employee_ranges: list[str] | None = None,
    authority_of: Callable[[str | None], float] | None = None,
) -> ScoringInput:
    # Optionally discount each evidence item's confidence by the authority of its
    # source (award document > news mention). Off by default to keep pure callers
    # unchanged; the live pipeline passes ``authority_for_url``.
    evidence_confs = [
        (ev.confidence if authority_of is None else ev.confidence * authority_of(ev.source_url))
        for ev in opportunity.supporting_evidence
        if ev.confidence is not None
    ]
    return ScoringInput(
        event_type=event.event_type,
        event_value=event.value_amount,
        event_date=event.event_date,
        event_sector=event.sector,
        company_industry=company.industry,
        company_employee_range=company.employee_range,
        target_sectors=target.sectors,
        target_min_value=target.min_value,
        ideal_employee_ranges=ideal_employee_ranges,
        opportunity_confidence=opportunity.confidence,
        evidence_confidences=evidence_confs,
        num_contacts=num_contacts,
        best_contact_seniority=best_contact_seniority,
    )
