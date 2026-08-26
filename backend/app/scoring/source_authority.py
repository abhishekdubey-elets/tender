"""Source authority weights.

Not all evidence is equally trustworthy: a government award document outranks a
news mention. These weights let scoring discount evidence by the authority of the
source it came from, so a lead backed by an official award scores above one backed
only by a newspaper report.

The values are initial engineering weights (0..1), not universal truths — the
system can calibrate them later against outcomes. They are applied multiplicatively
to an evidence item's confidence.
"""
from __future__ import annotations

from urllib.parse import urlsplit

# Ordered host-substring → authority. First match wins, so put the most specific
# (procurement/award, exchanges) before the broad gov.in / nic.in fallback.
_HOST_AUTHORITY: tuple[tuple[str, float], ...] = (
    # Government procurement / award systems — the strongest commercial signal.
    ("eprocure.gov.in", 1.00),
    ("gem.gov.in", 1.00),
    ("defprocurement", 1.00),
    # Central open-data API (official, structured).
    ("api.data.gov.in", 0.95),
    ("data.gov.in", 0.95),
    # Press Information Bureau.
    ("pib.gov.in", 0.98),
    # Stock-exchange corporate filings.
    ("bseindia.com", 0.97),
    ("nseindia.com", 0.97),
    # Regulators.
    ("rbi.org.in", 0.98),
    ("sebi.gov.in", 0.98),
    # Major business press (discovery / cross-check, not authoritative).
    ("economictimes", 0.85),
    ("business-standard", 0.85),
    ("livemint", 0.85),
    ("moneycontrol", 0.85),
    ("thehindubusinessline", 0.85),
    ("financialexpress", 0.85),
    ("reuters.com", 0.85),
)

# Broad fallbacks by host suffix, applied after the specific list above.
_GOV_SUFFIXES = (".gov.in", ".nic.in")

# Authority when the source is a government host not matched specifically.
GOV_DEFAULT = 0.96
# Authority when the source is some other reachable URL (assume news-ish/unknown).
UNKNOWN_URL_DEFAULT = 0.65
# Authority when there is no external URL (internal/rule-derived evidence): neutral.
NO_URL = 1.0


def authority_for_url(url: str | None) -> float:
    """Return the source-authority weight (0..1) for an evidence URL.

    ``None``/empty → 1.0 (neutral: internal or rule-derived evidence is not
    penalised). Recognised authoritative hosts get high weights; an unrecognised
    external host is treated as news-ish.
    """
    if not url:
        return NO_URL
    host = (urlsplit(url).netloc or url).lower()
    if not host:
        return NO_URL
    for needle, weight in _HOST_AUTHORITY:
        if needle in host:
            return weight
    if any(host.endswith(suffix) for suffix in _GOV_SUFFIXES):
        return GOV_DEFAULT
    return UNKNOWN_URL_DEFAULT
