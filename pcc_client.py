"""
PointClickCare client.

When USE_MOCK_DATA=true (or creds missing) this module returns canned data
from `mock_data`.  When live, it performs the standard OAuth2 client-
credentials flow against PCC Connect and then hits their REST endpoints.

The live implementation here is a scaffold: the endpoint paths are sensible
defaults and can be tuned once the PCC sandbox keys are issued.  The mock
path is feature-complete today.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx

import mock_data


class PCCClient:
    def __init__(self) -> None:
        self.use_mock = os.getenv("USE_MOCK_DATA", "true").lower() in ("1", "true", "yes")
        self.base_url = os.getenv("PCC_BASE_URL", "https://connect.pointclickcare.com").rstrip("/")
        self.oauth_url = os.getenv("PCC_OAUTH_URL", f"{self.base_url}/auth/token")
        self.customer_key = os.getenv("PCC_CUSTOMER_KEY")
        self.client_secret = os.getenv("PCC_CLIENT_SECRET")
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

        # If credentials missing, force mock mode to fail safely.
        if not self.use_mock and not (self.customer_key and self.client_secret):
            self.use_mock = True

    # ------------------------------------------------------------------ auth
    def _fetch_token(self) -> str:
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        resp = httpx.post(
            self.oauth_url,
            data={"grant_type": "client_credentials"},
            auth=(self.customer_key or "", self.client_secret or ""),
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def _get(self, path: str, params: Dict[str, Any] | None = None) -> Any:
        token = self._fetch_token()
        url = f"{self.base_url}{path}"
        resp = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------- accessors
    def get_facilities(self) -> List[Dict[str, Any]]:
        if self.use_mock:
            return mock_data.get_facilities()
        return self._get("/api/public/preview1/facilities").get("data", [])

    def get_patients(self, facility_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if self.use_mock:
            return mock_data.get_patients(facility_id)
        params: Dict[str, Any] = {}
        if facility_id:
            params["facId"] = facility_id
        return self._get("/api/public/preview1/patients", params=params).get("data", [])

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        if self.use_mock:
            return mock_data.get_patient(patient_id)
        return self._get(f"/api/public/preview1/patients/{patient_id}")

    def healthcheck(self) -> Dict[str, Any]:
        """Lightweight signal used by /health — does not consume quota."""
        return {
            "mode": "mock" if self.use_mock else "live",
            "base_url": self.base_url if not self.use_mock else None,
            "has_credentials": bool(self.customer_key and self.client_secret),
        }


pcc = PCCClient()

    def get_care_plans(self, patient_id: int):
        # MOCK
        if self.mock:
            return [
                {
                    "care_plan_id": 101,
                    "patient_id": patient_id,
                    "problem": "Patient has pain in lower back",
                    "status": "Active",
                    "goals": "Will improve pain level.",
                    "interventions": "Give meds. Assess pain.",
                    "responsible_discipline": "Nurse",
                    "start_date": "2026-04-01",
                    "target_date": ""
                },
                {
                    "care_plan_id": 102,
                    "patient_id": patient_id,
                    "problem": "Risk for falls due to weakness",
                    "status": "Active",
                    "goals": "Will not fall.",
                    "interventions": "Keep call bell in reach. Assist with transfers.",
                    "responsible_discipline": "",
                    "start_date": "2026-04-05",
                    "target_date": "2026-07-05"
                }
            ]
        return []

    def get_care_plan(self, patient_id: int, care_plan_id: int):
        # MOCK
        plans = self.get_care_plans(patient_id)
        for p in plans:
            if p["care_plan_id"] == care_plan_id:
                return p
        return None

    def update_care_plan(self, patient_id: int, care_plan_id: int, payload: dict):
        # MOCK
        return {"status": "success", "message": "Care plan updated in PCC", "care_plan_id": care_plan_id}
