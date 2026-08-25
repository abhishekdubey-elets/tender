"""SalesBriefGenerator: deterministic grounded brief, optional verified LLM prose."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.brief.facts import FactBook, build_factbook
from app.brief.llm import BriefLLMClient
from app.brief.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.brief.types import (
    LLM_EDITABLE,
    SECTION_ORDER,
    BriefInput,
    BriefMeta,
    SalesBrief,
    Section,
)
from app.brief.verify import find_unsupported_contacts, find_unsupported_numbers
from app.enrichment.types import EnrichmentField
from app.opportunity.rules import format_value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sec(key, title, text, is_inference, relies=None) -> Section:
    return Section(key=key, title=title, text=text, is_inference=is_inference, relies_on=relies or [])


class SalesBriefGenerator:
    def __init__(self, *, now: Callable[[], datetime] = _utcnow, max_attempts: int = 2) -> None:
        self._now = now
        self._max_attempts = max_attempts

    # ------------------------------------------------------------------ #
    def generate(self, inp: BriefInput, *, llm: BriefLLMClient | None = None) -> SalesBrief:
        fb = build_factbook(inp)
        sections = self._deterministic_sections(inp, fb)
        flags: list[str] = []
        mode = "deterministic"
        model = None
        in_tok = out_tok = None

        if llm is not None:
            mode = "llm"
            attempt = 0
            resp = None
            while attempt < self._max_attempts:
                attempt += 1
                resp = llm.compose(
                    system=SYSTEM_PROMPT,
                    user=build_user_prompt(inp, fb, {k: sections[k] for k in LLM_EDITABLE if k in sections}),
                    allowed_fact_ids=[f.id for f in fb.facts],
                )
                violations = self._verify(resp.sections, fb)
                if violations and attempt < self._max_attempts:
                    continue  # give the model another try
                break

            model, in_tok, out_tok = resp.model, resp.input_tokens, resp.output_tokens
            violations = self._verify(resp.sections, fb)
            for key in LLM_EDITABLE:
                proposed = resp.sections.get(key)
                if not proposed:
                    continue
                if key in violations:
                    # Unsupported claim → keep the grounded deterministic text, flag it.
                    # The offending token is NOT echoed, so it cannot leak into output.
                    flags.append(
                        f"{key}: {len(violations[key])} unsupported claim(s) detected and removed; "
                        "grounded text retained"
                    )
                    continue
                valid_ids = [fid for fid in proposed.get("fact_ids", []) if fid in fb.by_id]
                sections[key] = _sec(key, sections[key].title, proposed["text"],
                                     sections[key].is_inference, valid_ids or sections[key].relies_on)

        meta = BriefMeta(provider="anthropic", model=model, prompt_version=PROMPT_VERSION,
                         generated_at=self._now(), mode=mode, input_tokens=in_tok, output_tokens=out_tok)
        overall = (inp.score.total / 100) if inp.score else inp.opportunity.confidence
        return SalesBrief(
            sections=sections, verified_facts=fb.verified_facts(),
            overall_confidence=round(overall, 3), meta=meta,
            flags=flags, status="flagged" if flags else "ok",
        )

    # ------------------------------------------------------------------ #
    def _verify(self, llm_sections: dict, fb: FactBook) -> dict:
        violations: dict[str, list[str]] = {}
        for key, sec in llm_sections.items():
            if key not in LLM_EDITABLE:
                continue
            text = sec.get("text", "") if isinstance(sec, dict) else ""
            bad_nums = find_unsupported_numbers(text, fb)
            bad_contacts = find_unsupported_contacts(text, fb)
            bad_ids = [fid for fid in (sec.get("fact_ids", []) if isinstance(sec, dict) else []) if fid not in fb.by_id]
            issues = bad_nums + bad_contacts + [f"unknown fact id {b}" for b in bad_ids]
            if issues:
                violations[key] = issues
        return violations

    # ------------------------------------------------------------------ #
    def _deterministic_sections(self, inp: BriefInput, fb: FactBook) -> dict[str, Section]:
        ev, opp = inp.event, inp.opportunity
        company = inp.company_name
        event_ids = fb.ids_of_kind("event")

        # 1. Trigger
        awardee = ev.awardee or company
        et = ev.event_type.replace("_", " ")
        val = format_value(ev.value_amount, ev.currency)
        seg = f"{awardee} is linked to a {et}"
        if val:
            seg += f" worth {val}"
        if ev.sector:
            seg += f" in {ev.sector}"
        if ev.event_date:
            seg += f" ({ev.event_date.isoformat()})"
        trigger = _sec("trigger", "Trigger", seg + ".", False, event_ids)

        # 2. Why this company
        knowns = []
        if inp.enrichment:
            prof = inp.enrichment.profile
            for f, phrase in [(EnrichmentField.industry, "industry"), (EnrichmentField.hq_location, "HQ"),
                              (EnrichmentField.employee_range, "size"), (EnrichmentField.revenue, "revenue")]:
                fr = prof.get(f)
                if fr and fr.is_known:
                    knowns.append(f"{phrase} {fr.value}")
        why_company = (f"{company}: " + "; ".join(knowns) + "." if knowns
                       else f"Limited verified public data on {company}; confirm during discovery.")
        why_company_sec = _sec("why_this_company", "Why this company", why_company, False,
                               fb.ids_of_kind("company"))

        # 3. Why now
        reasons = []
        if ev.event_date:
            reasons.append(f"the event is dated {ev.event_date.isoformat()}")
        for f in ("signal.funding_signals", "signal.expansion_activity", "signal.recent_contracts"):
            if fb.ids_of_kind(f):
                reasons.append(f"recent {f.split('.')[1].replace('_', ' ')} reported")
        why_now = ("Timely because " + ", and ".join(reasons) + "."
                   if reasons else "Timing is uncertain — no recent dated signals are verified.")
        why_now_sec = _sec("why_now", "Why now", why_now, True, fb.ids_of_kind("event.date") + fb.ids_of_kind("signal"))

        # 4. Business need hypothesis
        need = (f"Hypothesis ({opp.epistemic_tier.name}): {opp.need_hypothesis}. {opp.reasoning}")
        need_sec = _sec("business_need", "Business need hypothesis", need, True, fb.ids_of_kind("need") + fb.ids_of_kind("opportunity"))

        # 5. Who to contact
        c = inp.contact
        if c and c.verified and c.name:
            who = f"{c.name}" + (f" — {c.title}" if c.title else "") + (f" ({c.source_url})" if c.source_url else "")
            who_sec = _sec("who_to_contact", "Who to contact", who + ".", False, fb.ids_of_kind("contact"))
        else:
            roles = ", ".join(opp.job_titles[:3]) or "relevant decision-makers"
            depts = ", ".join(opp.departments[:2])
            who = f"No specific contact verified yet. Target role(s): {roles}" + (f" in {depts}" if depts else "") + "."
            who_sec = _sec("who_to_contact", "Who to contact", who, True, [])

        # 6. Reason to call
        reason = (f"{company}'s {et} could create a {opp.need_hypothesis.lower()}, a timely fit for "
                  f"{opp.product_name}. Lead with that connection.")
        reason_sec = _sec("reason_to_call", "Reason to call", reason, True, fb.ids_of_kind("need"))

        # 7. Evidence (traceability)
        lines = [f"[{f.id}] {f.statement}" + (f" — {f.source_url}" if f.source_url else " — (no URL on file)")
                 for f in fb.verified_facts()]
        evidence_sec = _sec("evidence", "Evidence", "\n".join(lines) or "No verified evidence on file.", False,
                            [f.id for f in fb.verified_facts()])

        # 8. Confidence
        if inp.score:
            conf_txt = f"Lead score {inp.score.total}/100 (grade {inp.score.grade}); opportunity confidence {opp.confidence:.0%}."
        else:
            conf_txt = f"Opportunity confidence {opp.confidence:.0%} (no lead score computed)."
        confidence_sec = _sec("confidence", "Confidence", conf_txt, False, fb.ids_of_kind("score"))

        # 9. Recommended next action
        grade = inp.score.grade if inp.score else None
        if c and c.verified and c.name:
            action = f"Call {c.title or c.name} within {opp.timing}, leading with the trigger."
        elif grade in ("A", "B"):
            role = opp.job_titles[0] if opp.job_titles else "decision-maker"
            action = f"Prioritise: identify the {role} and reach out within {opp.timing}."
        elif grade == "C":
            action = "Nurture: gather stronger signals before outreach."
        else:
            action = "De-prioritise / monitor for stronger signals."
        action_sec = _sec("recommended_next_action", "Recommended next action", action, True, [])

        # Risk / uncertainty
        risks = [f"Assumption: {a}" for a in opp.assumptions]
        risks += [f"Alternative explanation: {a}" for a in opp.alternative_explanations]
        if opp.epistemic_tier.name != "fact":
            risks.append(f"The core need is an {opp.epistemic_tier.name}, not a verified fact.")
        if inp.enrichment:
            unknowns = [f.value for f in (EnrichmentField.industry, EnrichmentField.hq_location,
                                          EnrichmentField.employee_range, EnrichmentField.revenue)
                        if not (inp.enrichment.profile.get(f) and inp.enrichment.profile[f].is_known)]
            if unknowns:
                risks.append("Unverified company attributes: " + ", ".join(unknowns))
        if not (c and c.verified and c.name):
            risks.append("No verified decision-maker contact identified.")
        low_conf = [f.id for f in fb.facts if f.confidence is not None and f.confidence < 0.6]
        if low_conf:
            risks.append("Some evidence is low-confidence: " + ", ".join(low_conf))
        risk_txt = ("This lead may be incorrect if:\n- " + "\n- ".join(risks)) if risks else "No major risks identified."
        risk_sec = _sec("risk", "Risk / uncertainty", risk_txt, True, [])

        return {
            "trigger": trigger, "why_this_company": why_company_sec, "why_now": why_now_sec,
            "business_need": need_sec, "who_to_contact": who_sec, "reason_to_call": reason_sec,
            "evidence": evidence_sec, "confidence": confidence_sec,
            "recommended_next_action": action_sec, "risk": risk_sec,
        }
