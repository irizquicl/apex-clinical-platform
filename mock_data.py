"""
Mock dataset used when USE_MOCK_DATA=true.

60 patients across 3 SNF facilities.  Risk profiles are generated so that
each facility contains approximately:

    3  Critical  (>= 60)
    5  High      (40-59)
    7  Moderate  (20-39)
    5  Low       (< 20)

A seeded RNG keeps the dataset stable across restarts.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from risk_engine import score_patient, top_flags, recommended_actions

_RNG = random.Random(42)

# ---------------------------------------------------------------------------
# Facilities
# ---------------------------------------------------------------------------
FACILITIES: List[Dict[str, Any]] = [
    {
        "id": "autumn-lake-towson",
        "name": "Autumn Lake Towson",
        "short": "Towson",
        "beds": 120,
        "city": "Towson, MD",
        "last_risk_meeting": "Mar 10, 2026",
    },
    {
        "id": "autumn-lake-catonsville",
        "name": "Autumn Lake Catonsville",
        "short": "Catonsville",
        "beds": 98,
        "city": "Catonsville, MD",
        "last_risk_meeting": "Mar 12, 2026",
    },
    {
        "id": "complete-care-laurel",
        "name": "Complete Care Laurel",
        "short": "Laurel",
        "beds": 110,
        "city": "Laurel, MD",
        "last_risk_meeting": "Mar 11, 2026",
    },
]

FACILITY_INDEX = {f["id"]: f for f in FACILITIES}


# ---------------------------------------------------------------------------
# Demographic pools
# ---------------------------------------------------------------------------
_FIRST_NAMES = [
    "Margaret", "John", "Dorothy", "Robert", "Helen", "William",
    "Shirley", "Charles", "Doris", "James", "Betty", "Richard",
    "Joan", "Frank", "Barbara", "Joseph", "Mary", "George",
    "Ruth", "Edward", "Linda", "Thomas", "Patricia", "Harold",
    "Sandra", "Walter", "Nancy", "Ronald", "Carol", "Donald",
    "Alice", "Kenneth", "Gloria", "Raymond", "Dolores", "Gerald",
    "Elaine", "Louis", "Judith", "Stanley", "Anna", "Leonard",
    "Phyllis", "Vincent", "Irene", "Arthur", "Rose", "Eugene",
    "Frances", "Herbert", "Norma", "Ralph", "Virginia", "Paul",
    "Lillian", "Michael", "Ethel", "Henry", "Beatrice", "Clarence",
]

_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
    "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez",
    "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor",
    "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis",
    "Robinson",
]

_DIAGNOSES = [
    "CHF exacerbation", "COPD exacerbation", "Post-op hip repair",
    "UTI + delirium", "Pneumonia", "Dementia w/ behaviors",
    "DM2 + diabetic wound", "CVA rehab", "End-stage renal disease",
    "Parkinson disease", "Hip fracture", "Sepsis recovery",
    "Post-op knee replacement", "Atrial fibrillation",
    "Malnutrition / cachexia", "Acute kidney injury",
]

_PAYERS = ["Medicare A", "Medicare B", "Medicare Advantage", "Medicaid", "Private"]


# ---------------------------------------------------------------------------
# Profile archetypes — shape scores toward a target band
# ---------------------------------------------------------------------------
def _critical_features() -> Dict[str, Any]:
    """Score targeted ~65-90."""
    return {
        "fall_last_30d": True,
        "gait_unsteady": True,
        "psychotropics": True,
        "orthostatic_hypotension": _RNG.random() < 0.5,
        "pressure_ulcer_stage": _RNG.choice([2, 3, 3, 4]),
        "wound_infected": _RNG.random() < 0.6,
        "incontinence": True,
        "active_infection": True,
        "infection_type": _RNG.choice(["UTI", "pneumonia", "C. diff", "cellulitis"]),
        "fever_24h": True,
        "wbc_abnormal": True,
        "recent_antibiotic": True,
        "weight_loss_pct_30d": _RNG.uniform(7.0, 12.0),
        "albumin": round(_RNG.uniform(2.3, 2.9), 1),
        "poor_intake": True,
        "pain_score": _RNG.randint(6, 9),
        "prn_analgesic_frequent": True,
        "pain_uncontrolled": _RNG.random() < 0.5,
        "brief_stage": _RNG.choice(["moderate", "severe"]),
        "delirium": True,
        "behavioral_expressions": _RNG.random() < 0.6,
        "antipsychotic_new": _RNG.random() < 0.4,
        "adl_decline_30d": _RNG.randint(3, 5),
        "new_bed_bound": _RNG.random() < 0.5,
        "therapy_refusal": _RNG.random() < 0.4,
        "days_since_discharge": _RNG.randint(5, 25),
        "chronic_condition_count": _RNG.randint(4, 7),
        "er_visit_90d": True,
        "prior_readmission": _RNG.random() < 0.7,
        "active_med_count": _RNG.randint(14, 22),
        "high_risk_med": True,
        "recent_med_change": True,
        "drug_interaction_flag": _RNG.random() < 0.4,
        "advance_directive_on_file": False,
        "code_status": _RNG.choice(["", "", "DNR"]),
        "hospice_eligible": _RNG.random() < 0.5,
        "hospice_enrolled": False,
        "family_conflict": _RNG.random() < 0.3,
        "prognosis_poor": _RNG.random() < 0.5,
    }


def _high_features() -> Dict[str, Any]:
    """Score target ~40-58."""
    return {
        "fall_last_30d": _RNG.random() < 0.6,
        "gait_unsteady": True,
        "psychotropics": _RNG.random() < 0.6,
        "pressure_ulcer_stage": _RNG.choice([0, 1, 2]),
        "wound_infected": _RNG.random() < 0.2,
        "active_infection": _RNG.random() < 0.4,
        "infection_type": "UTI",
        "fever_24h": _RNG.random() < 0.3,
        "wbc_abnormal": _RNG.random() < 0.4,
        "recent_antibiotic": _RNG.random() < 0.6,
        "weight_loss_pct_30d": _RNG.uniform(4.0, 7.0),
        "albumin": round(_RNG.uniform(2.9, 3.4), 1),
        "poor_intake": _RNG.random() < 0.6,
        "pain_score": _RNG.randint(4, 7),
        "prn_analgesic_frequent": True,
        "brief_stage": _RNG.choice(["mild", "moderate"]),
        "delirium": _RNG.random() < 0.3,
        "behavioral_expressions": _RNG.random() < 0.4,
        "adl_decline_30d": _RNG.randint(1, 3),
        "new_bed_bound": False,
        "therapy_refusal": _RNG.random() < 0.3,
        "days_since_discharge": _RNG.randint(20, 60),
        "chronic_condition_count": _RNG.randint(3, 5),
        "er_visit_90d": _RNG.random() < 0.6,
        "prior_readmission": _RNG.random() < 0.4,
        "active_med_count": _RNG.randint(10, 14),
        "high_risk_med": _RNG.random() < 0.7,
        "recent_med_change": _RNG.random() < 0.6,
        "advance_directive_on_file": _RNG.random() < 0.4,
        "code_status": _RNG.choice(["Full code", "DNR", ""]),
    }


def _moderate_features() -> Dict[str, Any]:
    """Score target ~20-38."""
    return {
        "fall_last_30d": _RNG.random() < 0.5,
        "gait_unsteady": True,
        "psychotropics": _RNG.random() < 0.6,
        "pressure_ulcer_stage": _RNG.choice([0, 1, 1, 2]),
        "weight_loss_pct_30d": _RNG.uniform(3.0, 6.0),
        "albumin": round(_RNG.uniform(3.0, 3.5), 1),
        "poor_intake": _RNG.random() < 0.5,
        "pain_score": _RNG.randint(3, 6),
        "prn_analgesic_frequent": True,
        "brief_stage": _RNG.choice(["mild", "mild", "moderate"]),
        "behavioral_expressions": _RNG.random() < 0.3,
        "adl_decline_30d": _RNG.randint(1, 3),
        "days_since_discharge": _RNG.randint(20, 80),
        "chronic_condition_count": _RNG.randint(3, 5),
        "er_visit_90d": _RNG.random() < 0.5,
        "active_med_count": _RNG.randint(9, 13),
        "high_risk_med": _RNG.random() < 0.6,
        "recent_med_change": _RNG.random() < 0.5,
        "advance_directive_on_file": _RNG.random() < 0.5,
        "code_status": _RNG.choice(["Full code", "DNR", ""]),
    }


def _low_features() -> Dict[str, Any]:
    """Score target ~0-19."""
    return {
        "fall_last_30d": False,
        "gait_unsteady": _RNG.random() < 0.2,
        "psychotropics": _RNG.random() < 0.2,
        "pressure_ulcer_stage": 0,
        "pain_score": _RNG.randint(0, 3),
        "brief_stage": "none",
        "weight_loss_pct_30d": _RNG.uniform(0.0, 2.0),
        "albumin": round(_RNG.uniform(3.6, 4.2), 1),
        "chronic_condition_count": _RNG.randint(1, 3),
        "active_med_count": _RNG.randint(5, 9),
        "high_risk_med": _RNG.random() < 0.2,
        "advance_directive_on_file": True,
        "code_status": _RNG.choice(["Full code", "DNR"]),
    }


_BAND_BUILDERS = {
    "Critical": _critical_features,
    "High":     _high_features,
    "Moderate": _moderate_features,
    "Low":      _low_features,
}


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _iso_from_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _make_patient(pid: str, facility_id: str, band: str) -> Dict[str, Any]:
    first = _RNG.choice(_FIRST_NAMES)
    last = _RNG.choice(_LAST_NAMES)
    age = _RNG.randint(64, 96)
    gender = _RNG.choice(["M", "F", "F"])  # SNFs skew female
    room = f"{_RNG.randint(1, 4)}{_RNG.randint(0, 9)}{_RNG.randint(1, 9)}{_RNG.choice(['A', 'B'])}"
    features = _BAND_BUILDERS[band]()
    scored = score_patient(features)
    admit_days_ago = _RNG.randint(7, 240)
    md_visit_days_ago = _RNG.randint(1, 21) if band != "Critical" else _RNG.randint(5, 18)

    return {
        "id": pid,
        "facility_id": facility_id,
        "name": f"{first} {last}",
        "first_name": first,
        "last_name": last,
        "age": age,
        "gender": gender,
        "room": room,
        "primary_dx": _RNG.choice(_DIAGNOSES),
        "payer": _RNG.choice(_PAYERS),
        "admission_date": _iso_from_days_ago(admit_days_ago),
        "last_md_visit": _iso_from_days_ago(md_visit_days_ago),
        "md_days_since_visit": md_visit_days_ago,
        "features": features,
        "composite_score": scored["composite_score"],
        "risk_level": scored["risk_level"],
        "breakdown": scored["breakdown"],
        "top_flags": top_flags(scored),
        "recommended_actions": recommended_actions(scored),
        "vitals": {
            "bp":   f"{_RNG.randint(110, 160)}/{_RNG.randint(60, 95)}",
            "hr":   _RNG.randint(62, 110),
            "spo2": _RNG.randint(90, 99),
            "temp": round(_RNG.uniform(97.5, 100.8), 1),
            "weight_lb": _RNG.randint(105, 215),
        },
    }


def _generate() -> List[Dict[str, Any]]:
    patients: List[Dict[str, Any]] = []
    # Aim for 3 Critical / 5 High / 7 Moderate / 5 Low per facility  (20 * 3 = 60)
    bands = ["Critical"] * 3 + ["High"] * 5 + ["Moderate"] * 7 + ["Low"] * 5
    idx = 1
    for f in FACILITIES:
        _RNG.shuffle(bands)
        for band in bands:
            pid = f"p{idx:03d}"
            patients.append(_make_patient(pid, f["id"], band))
            idx += 1
    return patients


PATIENTS: List[Dict[str, Any]] = _generate()
PATIENT_INDEX: Dict[str, Dict[str, Any]] = {p["id"]: p for p in PATIENTS}


# ---------------------------------------------------------------------------
# Public accessors (shape == what pcc_client exposes for the live path)
# ---------------------------------------------------------------------------
def get_facilities() -> List[Dict[str, Any]]:
    """Return facility summaries with live census and risk distribution."""
    out = []
    for f in FACILITIES:
        roster = [p for p in PATIENTS if p["facility_id"] == f["id"]]
        dist = {"Critical": 0, "High": 0, "Moderate": 0, "Low": 0}
        for p in roster:
            dist[p["risk_level"]] += 1
        out.append({
            **f,
            "census": len(roster),
            "risk_distribution": dist,
            "avg_composite": round(sum(p["composite_score"] for p in roster) / max(len(roster), 1), 1),
        })
    return out


def get_patients(facility_id: str | None = None) -> List[Dict[str, Any]]:
    roster = PATIENTS
    if facility_id:
        roster = [p for p in roster if p["facility_id"] == facility_id]
    return roster


def get_patient(patient_id: str) -> Dict[str, Any] | None:
    return PATIENT_INDEX.get(patient_id)


def facility_by_id(facility_id: str) -> Dict[str, Any] | None:
    return FACILITY_INDEX.get(facility_id)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
