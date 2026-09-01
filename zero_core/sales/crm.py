"""Sales & Lead Management CRM Store for HR Recruitment AI Assistant."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SalesLead:
    lead_id: str = field(default_factory=lambda: f"lead_{uuid.uuid4().hex[:8]}")
    name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    recruiters_count: int = 1
    icp_type: str = "ICP_1_BOUTIQUE_AGENCY"
    status: str = "NEW_LEAD"  # NEW_LEAD, QUALIFIED, DEMO_BOOKED, TRIAL_ACTIVE, CONVERTED, CLOSED
    source: str = "WEBSITE_ORGANIC"
    selected_plan: str = "GROWTH_199"
    notes: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DemoBooking:
    booking_id: str = field(default_factory=lambda: f"demo_{uuid.uuid4().hex[:8]}")
    name: str = ""
    email: str = ""
    company: str = ""
    recruiters_count: int = 1
    requested_date: str = ""
    requested_time: str = ""
    status: str = "CONFIRMED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TrialSubscription:
    trial_id: str = field(default_factory=lambda: f"trial_{uuid.uuid4().hex[:8]}")
    lead_id: str = ""
    email: str = ""
    company: str = ""
    plan: str = "GROWTH_199"
    trial_start: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trial_end: str = field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    )
    is_active: bool = True
    converted: bool = False
    usage_stats: Dict[str, Any] = field(default_factory=lambda: {
        "resumes_parsed": 0,
        "interviews_copiloted": 0,
        "candidates_added": 0,
        "ai_queries_run": 0,
    })


class SalesCRMStore:
    """Manages persistent lead records, demo bookings, and 30-day trials."""

    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or Path(__file__).resolve().parents[1] / "data" / "sales_crm.json"
        self.leads: Dict[str, SalesLead] = {}
        self.demos: Dict[str, DemoBooking] = {}
        self.trials: Dict[str, TrialSubscription] = {}
        self._load()

    def _load(self) -> None:
        if self.data_path.exists():
            try:
                data = json.loads(self.data_path.read_text(encoding="utf-8"))
                for l in data.get("leads", []):
                    lead = SalesLead(**l)
                    self.leads[lead.lead_id] = lead
                for d in data.get("demos", []):
                    demo = DemoBooking(**d)
                    self.demos[demo.booking_id] = demo
                for t in data.get("trials", []):
                    trial = TrialSubscription(**t)
                    self.trials[trial.trial_id] = trial
            except Exception:
                pass

    def _save(self) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "leads": [asdict(l) for l in self.leads.values()],
            "demos": [asdict(d) for d in self.demos.values()],
            "trials": [asdict(t) for t in self.trials.values()],
        }
        self.data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def create_lead(
        self,
        name: str,
        email: str,
        company: str,
        phone: str = "",
        recruiters_count: int = 1,
        source: str = "WEBSITE",
        selected_plan: str = "GROWTH_199",
    ) -> SalesLead:
        # Determine ICP automatically
        if recruiters_count <= 3:
            icp = "ICP_1_BOUTIQUE_AGENCY"
        elif recruiters_count <= 15:
            icp = "ICP_2_MID_SIZED_AGENCY"
        elif recruiters_count <= 30:
            icp = "ICP_3_STARTUP_TECH"
        else:
            icp = "ICP_5_ENTERPRISE_STAFFING"

        lead = SalesLead(
            name=name,
            email=email,
            phone=phone,
            company=company,
            recruiters_count=recruiters_count,
            icp_type=icp,
            source=source,
            selected_plan=selected_plan,
        )
        self.leads[lead.lead_id] = lead
        self._save()
        return lead

    def book_demo(
        self,
        name: str,
        email: str,
        company: str,
        date: str,
        time: str,
        recruiters_count: int = 1,
    ) -> DemoBooking:
        demo = DemoBooking(
            name=name,
            email=email,
            company=company,
            recruiters_count=recruiters_count,
            requested_date=date,
            requested_time=time,
        )
        self.demos[demo.booking_id] = demo
        
        # Link or create lead
        existing = [l for l in self.leads.values() if l.email.lower() == email.lower()]
        if existing:
            existing[0].status = "DEMO_BOOKED"
        else:
            self.create_lead(name=name, email=email, company=company, recruiters_count=recruiters_count, source="DEMO_FORM")
        
        self._save()
        return demo

    def start_30_day_trial(
        self,
        name: str,
        email: str,
        company: str,
        plan: str = "GROWTH_199",
        recruiters_count: int = 1,
    ) -> TrialSubscription:
        lead = self.create_lead(
            name=name,
            email=email,
            company=company,
            recruiters_count=recruiters_count,
            source="30_DAY_TRIAL_SIGNUP",
            selected_plan=plan,
        )
        lead.status = "TRIAL_ACTIVE"

        trial = TrialSubscription(
            lead_id=lead.lead_id,
            email=email,
            company=company,
            plan=plan,
        )
        self.trials[trial.trial_id] = trial
        self._save()
        return trial

    def list_leads(self) -> List[SalesLead]:
        return list(self.leads.values())

    def list_trials(self) -> List[TrialSubscription]:
        return list(self.trials.values())

    def list_demos(self) -> List[DemoBooking]:
        return list(self.demos.values())


DEFAULT_SALES_CRM = SalesCRMStore()
