"""
Apex Clinical Intelligence Platform — FastAPI entry point.

Serves:
    /                       -> login page (static)
    /dashboard              -> main app shell (static, protected client-side)
    /static/*               -> CSS / JS / assets

    /health                 -> public health endpoint
    /auth/token             -> OAuth2 password-grant style login
    /auth/me                -> current user
    /api/facilities         -> facility summaries + risk distribution
    /api/kpis               -> top KPI row
    /api/triage             -> patient radar (sorted by risk)
    /api/patients/{id}      -> full patient record
    /api/patients/{id}/report -> printable HTML report
    /api/patients/{id}/interventions (POST) -> log intervention
    /api/patients/{id}/flag (POST/DELETE)   -> flag/unflag patient
    /api/feed               -> live action feed (synthesized)
"""

from __future__ import annotations

import html
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

import database
from pcc_client import pcc
from risk_engine import DOMAIN_LABELS

# ---------------------------------------------------------------------------
# Config / auth
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "apex-dev-secret-change-me-9f3e8a2c-72bd-4e10-a6d9-c17e8a1b2c3d")
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = 8

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hard-coded user table (MVP — swap for a real IdP later).  Passwords are
# hashed at import time so nothing in transit or at rest is plaintext.
USERS: Dict[str, Dict[str, Any]] = {
    "admin": {
        "username": "admin",
        "password_hash": _pwd.hash("ApexClinical2026!"),
        "role": "admin",
        "display_name": "Medical Director",
    },
    "viewer": {
        "username": "viewer",
        "password_hash": _pwd.hash("ApexView2026!"),
        "role": "viewer",
        "display_name": "Administrator",
    },
}

_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def _make_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def current_user(token: Optional[str] = Depends(_oauth2)) -> Dict[str, Any]:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    username = payload.get("sub")
    user = USERS.get(username) if username else None
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"],
    }


def require_admin(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Apex Clinical Intelligence Platform",
    version="1.0.0",
    description="Medical Director triage & clinical intelligence for Apex Healthcare SNFs.",
)

from care_plans import care_plan_router
app.include_router(care_plan_router)


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def _startup() -> None:
    database.init_db()


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def _root() -> RedirectResponse:
    return RedirectResponse("/login")


@app.get("/login", include_in_schema=False)
def _login_page() -> HTMLResponse:
    with open(os.path.join(STATIC_DIR, "login.html"), "r", encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


@app.get("/dashboard", include_in_schema=False)
def _dashboard_page() -> HTMLResponse:
    with open(os.path.join(STATIC_DIR, "dashboard.html"), "r", encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["system"])
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "apex-clinical-platform",
        "version": app.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_source": pcc.healthcheck(),
    }


# --------------------------------------------------------------------- auth
class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/auth/token", tags=["auth"])
def auth_token(
    request: Request,
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    body: Optional[LoginBody] = None,
) -> Dict[str, Any]:
    """Accept either form-urlencoded (OAuth2 style) or JSON."""
    if username is None or password is None:
        # Maybe they posted JSON
        if body is None:
            try:
                data = request.json()  # type: ignore[attr-defined]
            except Exception:
                data = None
            if isinstance(data, dict):
                username = data.get("username")
                password = data.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    user = USERS.get(username)
    if not user or not _pwd.verify(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _make_token(user["username"], user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_HOURS * 3600,
        "user": {
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"],
        },
    }


@app.get("/auth/me", tags=["auth"])
def auth_me(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    return user


# ------------------------------------------------------------------- facilities
@app.get("/api/facilities", tags=["data"])
def api_facilities(user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    rows = pcc.get_facilities()
    # add open alerts per facility via intervention log
    for r in rows:
        r["open_alerts"] = database.count_open_alerts(r["id"])
    return rows


# ------------------------------------------------------------------------- kpis
@app.get("/api/kpis", tags=["data"])
def api_kpis(
    facility_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    patients = pcc.get_patients(facility_id)
    critical = sum(1 for p in patients if p["risk_level"] == "Critical")
    high = sum(1 for p in patients if p["risk_level"] == "High")
    moderate = sum(1 for p in patients if p["risk_level"] == "Moderate")
    low = sum(1 for p in patients if p["risk_level"] == "Low")
    avg_md_visit = round(
        sum(p.get("md_days_since_visit", 0) for p in patients) / max(len(patients), 1), 1
    )
    readmits = sum(
        1 for p in patients if (p.get("features") or {}).get("days_since_discharge", 999) <= 30
    )
    return {
        "active_patients": len(patients),
        "critical": critical,
        "high_risk": high,
        "moderate_risk": moderate,
        "low_risk": low,
        "avg_md_visit_days": avg_md_visit,
        "readmit_window": readmits,
        "open_alerts": database.count_open_alerts(facility_id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ----------------------------------------------------------------------- triage
@app.get("/api/triage", tags=["data"])
def api_triage(
    facility_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: Dict[str, Any] = Depends(current_user),
) -> List[Dict[str, Any]]:
    roster = pcc.get_patients(facility_id)
    roster = sorted(roster, key=lambda p: p["composite_score"], reverse=True)[:limit]
    flagged = {f["patient_id"] for f in database.list_flags()}
    out = []
    import random
    for p in roster:
        # Seed random with patient ID for consistent labs
        rng = random.Random(p["id"])
        
        # Clinical Narrative
        flags_str = ", ".join(p["top_flags"]) if p["top_flags"] else "multiple interacting factors"
        narrative = f"Patient presents with a {p['risk_level'].lower()} risk profile (Score: {p['composite_score']}). Primary clinical drivers include {flags_str}. Review recent events and comorbidity burden for disposition planning."
        
        # Simulate Labs based on features to have something to interpret
        features = p.get("features", {})
        vitals = p.get("vitals", {})
        gender = p.get("gender", "M")
        
        # Lab interpretation dict
        lab_interp = {}
        
        # BMP
        if rng.random() < 0.2:
            lab_interp["Na"] = {"value": rng.randint(130, 135), "interpretation": "hyponatremia"}
        if rng.random() < 0.1:
            lab_interp["K"] = {"value": round(rng.uniform(5.1, 5.8), 1), "interpretation": "hyperkalemia"}
        elif rng.random() < 0.1:
            lab_interp["K"] = {"value": round(rng.uniform(3.0, 3.4), 1), "interpretation": "hypokalemia"}
            
        if features.get("wbc_abnormal"):
            lab_interp["WBC"] = {"value": round(rng.uniform(11.5, 16.0), 1), "interpretation": "leukocytosis"}
        
        cr_thresh = 1.3 if gender == "M" else 1.0
        if rng.random() < 0.3:
            lab_interp["Cr"] = {"value": round(rng.uniform(cr_thresh + 0.1, cr_thresh + 1.0), 1), "interpretation": "renal impairment"}
            lab_interp["BUN"] = {"value": rng.randint(26, 45), "interpretation": "elevated BUN"}
            
        if rng.random() < 0.25:
            lab_interp["Glucose"] = {"value": rng.randint(181, 250), "interpretation": "hyperglycemia"}
            
        if rng.random() < 0.2:
            hgb = rng.randint(8, 9)
            lab_interp["Hgb"] = {"value": hgb, "interpretation": "anemia"}
            
        if features.get("active_infection") and features.get("infection_type") == "UTI":
            lab_interp["UA"] = {"value": "Nitrites+, LE+", "interpretation": "likely UTI"}
            
        # Nursing Findings
        vital_flags = []
        temp = vitals.get("temp", 98.6)
        if temp > 100.4:
            vital_flags.append(f"Temp {temp} (Fever)")
        hr = vitals.get("hr", 80)
        if hr > 100:
            vital_flags.append(f"HR {hr} (Tachycardia)")
        spo2 = vitals.get("spo2", 98)
        if spo2 < 92:
            vital_flags.append(f"O2 {spo2}% (Hypoxia)")
            
        nf_summary = "Patient resting quietly, no acute distress noted over last shift."
        if features.get("poor_intake"):
            nf_summary = "Nursing reports poor PO intake. " + nf_summary
        if features.get("gait_unsteady"):
            nf_summary += " Unsteady gait observed during transfers."
            
        nursing_findings = {
            "summary": nf_summary,
            "vital_flags": vital_flags
        }
        
        # Plan of Care
        poc = []
        dx_str = p.get("primary_dx", "")
        cr_val = lab_interp.get("Cr", {}).get("value", 0)
        bun_val = lab_interp.get("BUN", {}).get("value", 0)
        if cr_val > 1.6 and bun_val > 20:
            poc.append("Monitor renal function: repeat BMP in 48-72h. Review nephrotoxic medications. Ensure adequate hydration. Consider holding ACE inhibitor/ARB if Cr rising >0.3 from baseline.")
            
        wbc_val = lab_interp.get("WBC", {}).get("value", 0)
        ua_interp = lab_interp.get("UA", {}).get("interpretation", "")
        if wbc_val > 11 and "UTI" in ua_interp:
            poc.append("Suspected UTI: obtain urine culture before starting antibiotics. Review current antibiotic coverage. If symptomatic, consider empiric treatment with facility antibiogram guidance.")
            
        if spo2 < 92 and ("COPD" in dx_str or "CHF" in dx_str):
            poc.append("Hypoxia management: assess for acute exacerbation vs baseline. Obtain CXR if not done in past 7 days. Consider supplemental O2 titration. INTERACT II Stop and Watch criteria met.")
            
        hgb_val = lab_interp.get("Hgb", {}).get("value", 15)
        if hgb_val < 10:
            poc.append("Anemia workup: review iron studies, B12, folate if not recent. Consider GI blood loss evaluation. Review anticoagulation dosing.")
            
        if p["composite_score"] > 85:
            poc.append("HIGH REHOSPITALIZATION RISK: Initiate INTERACT II protocol. Provider same-day review required. Consider family notification and goals of care discussion if appropriate.")
            
        glu_val = lab_interp.get("Glucose", {}).get("value", 100)
        if glu_val > 200:
            poc.append("Hyperglycemia: review sliding scale insulin coverage. Check HbA1c if not done in past 3 months. Consider endocrinology consult if persistent.")
            
        if temp > 100.4:
            poc.append("Fever workup: obtain blood cultures x2, UA/urine culture, CXR. Review current antibiotic coverage. Monitor for sepsis criteria (SIRS).")
            
        if features.get("fall_last_30d") or features.get("gait_unsteady"):
            poc.append("High fall risk: confirm bed alarm active, non-skid footwear in place, call light within reach. Review fall-risk medications. PT/OT consult for fall prevention program.")
            
        stage = features.get("pressure_ulcer_stage", 0)
        if stage > 0:
            poc.append("Pressure injury: confirm wound care orders in place. Ensure repositioning q2h protocol active. Nutrition consult for protein/calorie optimization. Wound care nurse follow-up this week.")
            
        if not poc:
            poc.append("Document findings in PCC progress note")
            poc.append("Review care plan alignment with current clinical status")
            
        poc.append("Notify attending physician of current risk level")

        out.append({
            "id": p["id"],
            "patient_name": p["name"],
            "age": p["age"],
            "gender": p["gender"],
            "room": p["room"],
            "facility_id": p["facility_id"],
            "facility_name": next(
                (f["name"] for f in pcc.get_facilities() if f["id"] == p["facility_id"]),
                "",
            ),
            "primary_dx": p["primary_dx"],
            "payer": p["payer"],
            "composite_score": p["composite_score"],
            "risk_level": p["risk_level"],
            "top_flags": p["top_flags"],
            "md_days_since_visit": p["md_days_since_visit"],
            "flagged": p["id"] in flagged,
            "clinical_narrative": narrative,
            "lab_interpretation": lab_interp,
            "nursing_findings": nursing_findings,
            "plan_of_care": poc,
        })
    return out


# ---------------------------------------------------------------------- patient
@app.get("/api/patients/{patient_id}", tags=["data"])
def api_patient(
    patient_id: str,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    p = pcc.get_patient(patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    flagged = database.is_flagged(patient_id)
    interventions = database.list_interventions(patient_id)
    facility = next((f for f in pcc.get_facilities() if f["id"] == p["facility_id"]), None)
    return {
        **p,
        "facility": facility,
        "flagged": flagged,
        "interventions": interventions,
    }


# ---------------------------------------------------------------- interventions
class InterventionBody(BaseModel):
    kind: str
    note: str = ""


@app.post("/api/patients/{patient_id}/interventions", tags=["data"])
def api_log_intervention(
    patient_id: str,
    body: InterventionBody,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    if not pcc.get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return database.log_intervention(patient_id, body.kind, body.note, user["username"])


# ----------------------------------------------------------------------- flags
class FlagBody(BaseModel):
    reason: str = ""


@app.post("/api/patients/{patient_id}/flag", tags=["data"])
def api_flag(
    patient_id: str,
    body: FlagBody,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    if not pcc.get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return database.flag_patient(patient_id, body.reason, user["username"])


@app.delete("/api/patients/{patient_id}/flag", tags=["data"])
def api_unflag(
    patient_id: str,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    removed = database.unflag_patient(patient_id)
    return {"removed": removed}


# ---------------------------------------------------------------- action feed
@app.get("/api/feed", tags=["data"])
def api_feed(user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    """Synthesize a live-activity feed from interventions + high-risk patients."""
    feed: List[Dict[str, Any]] = []
    # recent interventions
    for iv in database.list_interventions()[:10]:
        kind_pretty = iv["kind"].replace("_", " ").title()
        if kind_pretty.lower().startswith("md "):
            kind_pretty = "MD" + kind_pretty[2:]
        feed.append({
            "tone": "indigo",
            "time_label": iv["created_at"][:16].replace("T", " "),
            "title": f"{kind_pretty} logged",
            "detail": iv["note"] or f"Intervention for patient {iv['patient_id']}",
        })
    # surface critical patients
    for p in pcc.get_patients():
        if p["risk_level"] != "Critical":
            continue
        feed.append({
            "tone": "red",
            "time_label": "now",
            "title": f"Critical · {p['name']} · Room {p['room']}",
            "detail": ", ".join(p["top_flags"][:2]) or "Composite score " + str(p["composite_score"]),
        })
    # pad with a couple of operational items
    feed.append({
        "tone": "green",
        "time_label": "today",
        "title": "Risk meeting complete",
        "detail": "All three facilities reviewed this week.",
    })
    return feed[:12]


# -------------------------------------------------------------- patient report
@app.get("/api/patients/{patient_id}/report", response_class=HTMLResponse, tags=["data"])
def api_patient_report(
    patient_id: str,
    user: Dict[str, Any] = Depends(current_user),
) -> HTMLResponse:
    p = pcc.get_patient(patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    facility = next((f for f in pcc.get_facilities() if f["id"] == p["facility_id"]), None)
    body = _render_report_html(p, facility)
    return HTMLResponse(body)


def _render_report_html(p: Dict[str, Any], facility: Optional[Dict[str, Any]]) -> str:
    band = p["risk_level"]
    colors = {"Critical": "#EF4444", "High": "#F59E0B", "Moderate": "#6366F1", "Low": "#10B981"}
    c = colors.get(band, "#64748B")
    rows = []
    for key, v in p["breakdown"].items():
        flag_html = "".join(f"<li>{html.escape(f)}</li>" for f in v["flags"]) or "<li>No flags</li>"
        rows.append(f"""
            <tr>
              <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">
                  <div style="font-weight:600;color:#0F172A">{html.escape(v['label'])}</div>
              </td>
              <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;width:120px;">
                  <div style="display:flex;align-items:center;gap:8px;">
                    <div style="flex:1;background:#E2E8F0;height:8px;border-radius:4px;overflow:hidden;">
                      <div style="width:{v['score']*10}%;background:{c};height:100%;"></div>
                    </div>
                    <span style="font-weight:600;color:#0F172A;font-variant-numeric:tabular-nums;">{v['score']}/10</span>
                  </div>
              </td>
              <td style="padding:10px 12px;border-bottom:1px solid #E2E8F0;">
                  <ul style="margin:0;padding-left:18px;color:#334155;font-size:13px;">{flag_html}</ul>
              </td>
            </tr>
        """)
    actions_html = "".join(f"<li>{html.escape(a)}</li>" for a in p["recommended_actions"])
    fname = facility["name"] if facility else "—"
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Patient Report — {html.escape(p['name'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *{{box-sizing:border-box;font-family:'Inter',sans-serif;}}
  body{{margin:0;background:#F8F9FC;color:#0F172A;padding:36px;}}
  .sheet{{max-width:900px;margin:0 auto;background:#fff;border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,0.05);}}
  .header{{background:#6366F1;color:#fff;padding:28px 32px;display:flex;justify-content:space-between;align-items:flex-start;}}
  .header h1{{margin:0 0 6px;font-size:22px;font-weight:700;}}
  .header .meta{{font-size:13px;opacity:.85;}}
  .pill{{display:inline-block;padding:4px 12px;border-radius:999px;font-size:12px;font-weight:600;background:rgba(255,255,255,.2);}}
  .score{{font-size:48px;font-weight:700;line-height:1;}}
  .body{{padding:28px 32px;}}
  h3{{margin:24px 0 12px;font-size:14px;text-transform:uppercase;color:#64748B;letter-spacing:.5px;font-weight:600;}}
  table{{width:100%;border-collapse:collapse;font-size:13px;}}
  .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px;}}
  .grid .cell{{background:#F8FAFC;padding:14px 16px;border-radius:8px;border:1px solid #E2E8F0;}}
  .grid .cell .label{{font-size:11px;text-transform:uppercase;color:#64748B;letter-spacing:.5px;font-weight:600;}}
  .grid .cell .val{{font-size:15px;font-weight:600;margin-top:4px;}}
  ul{{font-size:13px;color:#334155;line-height:1.6;}}
  .footer{{padding:18px 32px;border-top:1px solid #E2E8F0;color:#64748B;font-size:11px;text-transform:uppercase;letter-spacing:.6px;text-align:center;}}
  @media print{{ body{{background:#fff;padding:0;}} .sheet{{border:none;box-shadow:none;}} }}
</style>
</head>
<body>
<div class="sheet">
  <div class="header" style="background:{c}">
    <div>
      <h1>{html.escape(p['name'])}</h1>
      <div class="meta">Room {html.escape(p['room'])} · {p['age']}{p['gender']} · {html.escape(p['primary_dx'])}</div>
      <div class="meta" style="margin-top:4px;">{html.escape(fname)} · Payer: {html.escape(p['payer'])}</div>
    </div>
    <div style="text-align:right;">
      <span class="pill">{band}</span>
      <div class="score">{p['composite_score']}</div>
      <div class="meta">Composite / 100</div>
    </div>
  </div>
  <div class="body">
    <div class="grid">
      <div class="cell"><div class="label">Admission</div><div class="val">{html.escape(str(p.get('admission_date','')))}</div></div>
      <div class="cell"><div class="label">Last MD visit</div><div class="val">{p['md_days_since_visit']} days ago</div></div>
      <div class="cell"><div class="label">Active meds</div><div class="val">{(p.get('features') or {}).get('active_med_count','—')}</div></div>
    </div>
    <h3>Risk domain breakdown</h3>
    <table>
      <thead><tr>
        <th style="text-align:left;padding:10px 12px;font-size:11px;text-transform:uppercase;color:#64748B;border-bottom:1px solid #E2E8F0;">Domain</th>
        <th style="text-align:left;padding:10px 12px;font-size:11px;text-transform:uppercase;color:#64748B;border-bottom:1px solid #E2E8F0;">Score</th>
        <th style="text-align:left;padding:10px 12px;font-size:11px;text-transform:uppercase;color:#64748B;border-bottom:1px solid #E2E8F0;">Clinical flags</th>
      </tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    <h3>Recommended actions</h3>
    <ul>{actions_html}</ul>
  </div>
  <div class="footer">Apex Healthcare Advanced Medicine Division · Report generated {datetime.now(timezone.utc).strftime('%b %d, %Y %H:%M UTC')}</div>
</div>
<script>setTimeout(()=>{{try{{window.print();}}catch(e){{}}}},350);</script>
</body>
</html>"""
