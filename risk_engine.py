"""
Apex Clinical Intelligence — 10-domain risk scoring engine.

Each domain is scored 0-10 based on clinical features extracted from the
patient record.  The composite score is the sum (max 100) mapped to bands:

    Critical  >= 60
    High      40-59
    Moderate  20-39
    Low       < 20
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Domain catalog
# ---------------------------------------------------------------------------
DOMAINS: List[Tuple[str, str]] = [
    ("fall",         "Fall Risk"),
    ("wound",        "Wound / Skin"),
    ("infection",    "Infection / Sepsis"),
    ("nutrition",    "Nutrition / Weight"),
    ("pain",         "Pain"),
    ("cognition",    "Cognition / Behavioral"),
    ("functional",   "Functional Decline"),
    ("readmission",  "Readmission Risk"),
    ("medication",   "Medication Safety"),
    ("goals",        "Goals of Care"),
]

DOMAIN_KEYS = [k for k, _ in DOMAINS]
DOMAIN_LABELS = {k: v for k, v in DOMAINS}


# ---------------------------------------------------------------------------
# Domain scorers — each returns (score_0_to_10, list_of_supporting_flags)
# ---------------------------------------------------------------------------
def _fall(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    if p.get("fall_last_30d"):
        score += 5
        flags.append("Fall in last 30 days")
    if p.get("gait_unsteady"):
        score += 2
        flags.append("Unsteady gait")
    if p.get("psychotropics"):
        score += 2
        flags.append("On psychotropic medication")
    if p.get("orthostatic_hypotension"):
        score += 2
        flags.append("Orthostatic hypotension")
    if p.get("assistive_device") == "none" and p.get("mobility_limited"):
        score += 1
        flags.append("Mobility limited, no assistive device")
    return min(score, 10), flags


def _wound(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    stage = p.get("pressure_ulcer_stage", 0) or 0
    if stage >= 3:
        score += 6
        flags.append(f"Stage {stage} pressure ulcer")
    elif stage == 2:
        score += 4
        flags.append("Stage 2 pressure ulcer")
    elif stage == 1:
        score += 2
        flags.append("Stage 1 pressure ulcer")
    if p.get("wound_infected"):
        score += 3
        flags.append("Wound with signs of infection")
    if p.get("incontinence") and stage > 0:
        score += 1
        flags.append("Incontinence with open wound")
    return min(score, 10), flags


def _infection(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    if p.get("active_infection"):
        score += 5
        flags.append(f"Active infection: {p.get('infection_type', 'unspecified')}")
    if p.get("fever_24h"):
        score += 2
        flags.append("Fever within 24h")
    if p.get("wbc_abnormal"):
        score += 2
        flags.append("Abnormal WBC")
    if p.get("recent_antibiotic"):
        score += 1
        flags.append("Recent antibiotic course")
    return min(score, 10), flags


def _nutrition(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    wt_loss = p.get("weight_loss_pct_30d") or 0
    if wt_loss >= 7.5:
        score += 5
        flags.append(f"Weight loss {wt_loss:.1f}% in 30d")
    elif wt_loss >= 5:
        score += 3
        flags.append(f"Weight loss {wt_loss:.1f}% in 30d")
    albumin = p.get("albumin")
    if albumin is not None and albumin < 3.0:
        score += 3
        flags.append(f"Albumin {albumin} g/dL")
    elif albumin is not None and albumin < 3.5:
        score += 1
        flags.append(f"Albumin {albumin} g/dL (borderline)")
    if p.get("poor_intake"):
        score += 2
        flags.append("Poor PO intake")
    return min(score, 10), flags


def _pain(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    pain = p.get("pain_score") or 0
    if pain >= 7:
        score += 6
        flags.append(f"Pain {pain}/10")
    elif pain >= 4:
        score += 3
        flags.append(f"Pain {pain}/10")
    elif pain >= 1:
        score += 1
        flags.append(f"Pain {pain}/10")
    if p.get("prn_analgesic_frequent"):
        score += 2
        flags.append("Frequent PRN analgesic use")
    if p.get("pain_uncontrolled"):
        score += 2
        flags.append("Pain uncontrolled on current regimen")
    return min(score, 10), flags


def _cognition(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    brief = p.get("brief_stage")  # none / mild / moderate / severe
    levels = {"mild": 2, "moderate": 4, "severe": 6}
    if brief in levels:
        score += levels[brief]
        flags.append(f"Cognition: {brief} impairment")
    if p.get("delirium"):
        score += 3
        flags.append("Delirium documented")
    if p.get("behavioral_expressions"):
        score += 2
        flags.append("Behavioral expressions (agitation/aggression)")
    if p.get("antipsychotic_new"):
        score += 1
        flags.append("New antipsychotic started")
    return min(score, 10), flags


def _functional(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    adl = p.get("adl_decline_30d") or 0  # ADL points lost in 30d
    if adl >= 4:
        score += 5
        flags.append(f"ADL decline {adl} points in 30d")
    elif adl >= 2:
        score += 3
        flags.append(f"ADL decline {adl} points in 30d")
    if p.get("new_bed_bound"):
        score += 3
        flags.append("New bed-bound status")
    if p.get("therapy_refusal"):
        score += 2
        flags.append("Therapy refusal")
    return min(score, 10), flags


def _readmission(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    days = p.get("days_since_discharge")
    if days is not None and days <= 30:
        score += 4
        flags.append(f"Post-discharge day {days} (30-day window)")
    chronic = p.get("chronic_condition_count") or 0
    if chronic >= 4:
        score += 3
        flags.append(f"{chronic} chronic conditions")
    elif chronic >= 2:
        score += 1
        flags.append(f"{chronic} chronic conditions")
    if p.get("er_visit_90d"):
        score += 2
        flags.append("ER visit within 90 days")
    if p.get("prior_readmission"):
        score += 2
        flags.append("Prior 30-day readmission")
    return min(score, 10), flags


def _medication(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    meds = p.get("active_med_count") or 0
    if meds >= 15:
        score += 4
        flags.append(f"Polypharmacy ({meds} active meds)")
    elif meds >= 10:
        score += 2
        flags.append(f"Polypharmacy ({meds} active meds)")
    if p.get("high_risk_med"):
        score += 3
        flags.append("High-risk medication (anticoag / opioid / insulin)")
    if p.get("recent_med_change"):
        score += 1
        flags.append("Medication changed in last 7 days")
    if p.get("drug_interaction_flag"):
        score += 2
        flags.append("Potential drug-drug interaction")
    return min(score, 10), flags


def _goals(p: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []
    if not p.get("advance_directive_on_file"):
        score += 2
        flags.append("No advance directive on file")
    if not p.get("code_status"):
        score += 2
        flags.append("Code status undocumented")
    if p.get("hospice_eligible") and not p.get("hospice_enrolled"):
        score += 4
        flags.append("Hospice-eligible but not enrolled")
    if p.get("family_conflict"):
        score += 2
        flags.append("Family conflict re: care goals")
    if p.get("prognosis_poor"):
        score += 2
        flags.append("Poor short-term prognosis")
    return min(score, 10), flags


_SCORERS = {
    "fall":        _fall,
    "wound":       _wound,
    "infection":   _infection,
    "nutrition":   _nutrition,
    "pain":        _pain,
    "cognition":   _cognition,
    "functional":  _functional,
    "readmission": _readmission,
    "medication":  _medication,
    "goals":       _goals,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def risk_band(score: int) -> str:
    if score >= 60:
        return "Critical"
    if score >= 40:
        return "High"
    if score >= 20:
        return "Moderate"
    return "Low"


def score_patient(features: Dict[str, Any]) -> Dict[str, Any]:
    """Return full scored breakdown for a single patient feature dict."""
    breakdown: Dict[str, Any] = {}
    total = 0
    for key, label in DOMAINS:
        s, flags = _SCORERS[key](features)
        breakdown[key] = {"label": label, "score": s, "flags": flags}
        total += s
    return {
        "composite_score": total,
        "risk_level": risk_band(total),
        "breakdown": breakdown,
    }


def top_flags(scored: Dict[str, Any], limit: int = 3) -> List[str]:
    """Pull the N highest-scoring domain labels for a quick summary."""
    rows = sorted(
        scored["breakdown"].items(),
        key=lambda kv: kv[1]["score"],
        reverse=True,
    )
    out: List[str] = []
    for _, v in rows:
        if v["score"] >= 3:
            out.append(v["label"])
        if len(out) >= limit:
            break
    return out


def recommended_actions(scored: Dict[str, Any]) -> List[str]:
    """High-level action recommendations based on the highest scoring domains."""
    actions: List[str] = []
    bd = scored["breakdown"]
    if bd["fall"]["score"] >= 6:
        actions.append("Review fall-prevention plan; evaluate PT consult and bed alarm.")
    if bd["wound"]["score"] >= 6:
        actions.append("Wound care specialist consult; reposition q2h and update Tx.")
    if bd["infection"]["score"] >= 6:
        actions.append("Sepsis bundle / culture & sensitivity; notify MD within 2h.")
    if bd["nutrition"]["score"] >= 6:
        actions.append("RD consult; consider calorie counts and supplements.")
    if bd["pain"]["score"] >= 6:
        actions.append("Pain regimen review; consider scheduled vs PRN escalation.")
    if bd["cognition"]["score"] >= 6:
        actions.append("Delirium workup (CAM); review psychotropics and environment.")
    if bd["functional"]["score"] >= 6:
        actions.append("Therapy re-eval; restorative nursing plan.")
    if bd["readmission"]["score"] >= 6:
        actions.append("TCM follow-up; medication reconciliation within 48h.")
    if bd["medication"]["score"] >= 6:
        actions.append("Pharmacist-led medication review; check interactions.")
    if bd["goals"]["score"] >= 6:
        actions.append("Goals-of-care conversation; confirm code status & AD.")
    if not actions:
        actions.append("Continue current care plan; re-screen at next MDS cycle.")
    return actions
