"""Thesis Filter & Scoring Engine.

Implements the five tri-state thesis filters, the additive/penalty scoring
function, and the classifier. Scoring is conservative: ambiguity lowers the
score (penalty) rather than raising it, and only filters evaluated as ``True``
contribute positive points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import ThesisConfig
from .models import Classification, Company, Deal, Founder, ThesisMatch
from .normalizer import best_estimate_ev

# Point weights (design Requirement 8).
SECTOR_POINTS = 25
AGE_POINTS = 20
FINANCIAL_POINTS = 20
FOUNDER_POINTS = 15
AI_POINTS = 10
MAX_PENALTY = 20

CORE_THRESHOLD = 70
REJECT_THRESHOLD = 40


@dataclass
class FilterResults:
    """Tri-state outcomes for the five thesis filters."""

    passes_age_filter: Optional[bool] = None
    passes_sector_filter: Optional[bool] = None
    passes_financial_filter: Optional[bool] = None
    passes_founder_filter: Optional[bool] = None
    ai_automation_potential_flag: Optional[bool] = None


def _is_preferred_sector(sector: str, config: ThesisConfig) -> bool:
    s = sector.lower()
    return any(pref in s or s in pref for pref in config.preferred_sectors)


def _max_tenure(founders: list[Founder]) -> Optional[int]:
    tenures = [f.tenure_years for f in founders if f.tenure_years is not None]
    return max(tenures) if tenures else None


def evaluate_filters(
    company: Company,
    deal: Deal,
    founders: list[Founder],
    config: ThesisConfig,
) -> FilterResults:
    """Evaluate all five thesis filters as tri-state values."""

    f = FilterResults()

    # --- Age filter ---
    if company.founded_year is None:
        f.passes_age_filter = None
    elif (config.current_year - company.founded_year) >= config.min_trading_years:
        f.passes_age_filter = True
    else:
        f.passes_age_filter = False

    # --- Sector filter --- (banned always wins)
    if company.banned_sector_flag:
        f.passes_sector_filter = False
    elif company.sector is None:
        f.passes_sector_filter = None
    elif _is_preferred_sector(company.sector, config):
        f.passes_sector_filter = True
    else:
        # Allowed-if-stable: unknown until further evidence.
        f.passes_sector_filter = None

    # --- Financial filter ---
    revenue, ebitda, asking = deal.revenue, deal.ebitda, deal.asking_price
    if revenue is not None and ebitda is not None and (
        revenue >= config.min_revenue_usd and ebitda >= config.min_ebitda_usd
    ):
        f.passes_financial_filter = True
    elif _implies_healthy_mid_market(deal, config):
        f.passes_financial_filter = True
    elif revenue is None and ebitda is None and asking is None:
        f.passes_financial_filter = None
    else:
        f.passes_financial_filter = False

    # --- Founder filter ---
    best_tenure = _max_tenure(founders)
    if best_tenure is None:
        f.passes_founder_filter = None
    elif best_tenure >= config.min_founder_tenure_years:
        f.passes_founder_filter = True
    else:
        f.passes_founder_filter = False

    # --- AI / automation potential ---
    notes = (deal.ai_automation_potential_notes or "").lower()
    if "automation upside" in notes:
        f.ai_automation_potential_flag = True
    elif "asset-heavy" in notes or "low-complexity" in notes:
        f.ai_automation_potential_flag = False
    else:
        f.ai_automation_potential_flag = None

    return f


def _implies_healthy_mid_market(deal: Deal, config: ThesisConfig) -> bool:
    """True when EV sits in the core range and margins look healthy."""

    ev = best_estimate_ev(deal)
    if ev is None:
        return False
    if not (config.ev_core_min <= ev <= config.ev_core_max):
        return False
    if deal.revenue is not None and deal.ebitda is not None and deal.revenue > 0:
        margin = deal.ebitda / deal.revenue
        return margin >= 0.10
    # EV in core range with no contradicting margin info -> healthy mid-market.
    return True


def assess_data_quality(company: Company, deal: Deal, founders: list[Founder]) -> int:
    """Return a missing-information penalty in ``[0, MAX_PENALTY]``."""

    penalty = 0
    if company.sector is None:
        penalty += 5
    if company.founded_year is None:
        penalty += 4
    if deal.revenue is None and deal.ebitda is None and deal.asking_price is None:
        penalty += 8
    if not founders:
        penalty += 3
    if deal.listing_date == "unknown_date" and deal.last_seen_at == "unknown_date":
        penalty += 3
    return min(MAX_PENALTY, penalty)


def compute_score(f: FilterResults, missing_penalty: int) -> int:
    """Additive score with capped penalty, clamped to ``[0, 100]``."""

    score = 0
    if f.passes_sector_filter is True:
        score += SECTOR_POINTS
    if f.passes_age_filter is True:
        score += AGE_POINTS
    if f.passes_financial_filter is True:
        score += FINANCIAL_POINTS
    if f.passes_founder_filter is True:
        score += FOUNDER_POINTS
    if f.ai_automation_potential_flag is True:
        score += AI_POINTS

    score -= min(MAX_PENALTY, max(0, missing_penalty))

    if score < 0:
        score = 0
    if score > 100:
        score = 100
    return score


def _clearly_too_large(deal: Deal, config: ThesisConfig) -> bool:
    ev = best_estimate_ev(deal)
    return ev is not None and ev > config.ev_absolute_max


def _has_exclusion_flag(f: FilterResults, deal: Deal, config: ThesisConfig) -> bool:
    return f.passes_sector_filter is False or _clearly_too_large(deal, config)


def _exactly_one_key_filter_unknown(f: FilterResults) -> bool:
    key = [
        f.passes_age_filter,
        f.passes_sector_filter,
        f.passes_financial_filter,
        f.passes_founder_filter,
    ]
    unknown = sum(1 for v in key if v is None)
    others_strong = all(v is True for v in key if v is not None)
    return unknown == 1 and others_strong


def classify(
    score: int,
    f: FilterResults,
    deal: Deal,
    config: ThesisConfig,
) -> Classification:
    """Classify a deal. Hard exclusions dominate every other consideration."""

    # Hard exclusions take absolute precedence.
    if f.passes_sector_filter is False:
        return Classification.reject
    if _clearly_too_large(deal, config):
        return Classification.reject
    if score < REJECT_THRESHOLD:
        return Classification.reject

    if score >= CORE_THRESHOLD and not _has_exclusion_flag(f, deal, config):
        return Classification.core_thesis

    # 40 <= score < 70 -> adjacent; also the one-key-unknown strong path.
    return Classification.adjacent_thesis


def _explain(
    f: FilterResults,
    score: int,
    classification: Classification,
    deal: Deal,
    company: Company,
    config: ThesisConfig,
) -> str:
    parts: list[str] = []

    def label(name: str, val: Optional[bool]) -> str:
        state = {True: "pass", False: "fail", None: "unknown"}[val]
        return f"{name}={state}"

    if classification is Classification.reject:
        if f.passes_sector_filter is False:
            if company.banned_sector_flag:
                parts.append("Rejected: company is in an excluded sector (tobacco/liquor/gambling).")
            else:
                parts.append("Rejected: sector filter failed.")
        elif _clearly_too_large(deal, config):
            parts.append(
                "Rejected: estimated enterprise value clearly exceeds the absolute maximum (~50M)."
            )
        else:
            parts.append(f"Rejected: overall score {score} is below the inclusion threshold of 40.")
    elif classification is Classification.core_thesis:
        parts.append(
            f"Core thesis: score {score} with no exclusion flags; strong alignment across thesis filters."
        )
    else:
        parts.append(
            f"Adjacent thesis: score {score} indicates a partial fit; some filters are unknown or weaker."
        )

    parts.append(
        "Filters ["
        + ", ".join(
            [
                label("sector", f.passes_sector_filter),
                label("age", f.passes_age_filter),
                label("financial", f.passes_financial_filter),
                label("founder", f.passes_founder_filter),
                label("ai_automation", f.ai_automation_potential_flag),
            ]
        )
        + f"]; deal_size={deal.deal_size_bucket.value}."
    )
    return " ".join(parts)


def build_thesis_match(
    f: FilterResults,
    score: int,
    classification: Classification,
    deal: Deal,
    company: Company,
    config: ThesisConfig,
) -> ThesisMatch:
    """Assemble the :class:`ThesisMatch` embedded in a deal."""

    return ThesisMatch(
        passes_age_filter=f.passes_age_filter,
        passes_sector_filter=f.passes_sector_filter,
        passes_financial_filter=f.passes_financial_filter,
        passes_founder_filter=f.passes_founder_filter,
        ai_automation_potential_flag=f.ai_automation_potential_flag,
        overall_score=score,
        classification=classification,
        explanation=_explain(f, score, classification, deal, company, config),
    )
