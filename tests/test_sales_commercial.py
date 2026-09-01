"""Tests for Sales Agent, Lead CRM, and Commercial APIs."""

import pytest
from fastapi.testclient import TestClient
from zero_core.interfaces.web.app import app
from zero_core.sales.crm import DEFAULT_SALES_CRM, SalesCRMStore
from zero_core.agents.sales_agent import DEFAULT_SALES_AGENT

client = TestClient(app)


def test_sales_crm_lead_creation():
    crm = SalesCRMStore()
    lead = crm.create_lead(
        name="Sarah Jenkins",
        email="sarah@apexrecruiting.com",
        company="Apex Recruiting",
        recruiters_count=4,
        selected_plan="GROWTH_199",
    )
    assert lead.lead_id.startswith("lead_")
    assert lead.icp_type == "ICP_2_MID_SIZED_AGENCY"
    assert lead.status == "NEW_LEAD"


def test_sales_crm_30_day_trial():
    crm = SalesCRMStore()
    trial = crm.start_30_day_trial(
        name="Alex Turner",
        email="alex@turnerheadhunters.com",
        company="Turner Search",
        plan="STARTER_79",
        recruiters_count=2,
    )
    assert trial.trial_id.startswith("trial_")
    assert trial.is_active is True
    assert trial.plan == "STARTER_79"


def test_sales_agent_campaign_generation():
    ig_camp = DEFAULT_SALES_AGENT.generate_marketing_campaign("instagram")
    assert ig_camp["channel"] == "Instagram"
    assert len(ig_camp["slides"]) == 5

    li_camp = DEFAULT_SALES_AGENT.generate_marketing_campaign("linkedin")
    assert li_camp["channel"] == "LinkedIn"
    assert "HR Recruitment AI Assistant" in li_camp["post_body"]

    wa_camp = DEFAULT_SALES_AGENT.generate_marketing_campaign("whatsapp")
    assert wa_camp["channel"] == "WhatsApp"


def test_web_sales_api_endpoints():
    # 1. Capture Lead
    res = client.post(
        "/api/v1/sales/lead",
        json={"name": "Marcus Vance", "email": "marcus@vance.io", "company": "Vance AI", "recruiters_count": 8},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "SUCCESS"

    # 2. Book Demo
    res2 = client.post(
        "/api/v1/sales/demo",
        json={"name": "Elena Rostova", "email": "elena@globalhr.com", "company": "Global HR", "requested_date": "2026-09-01"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "SUCCESS"

    # 3. 30-Day Trial Signup
    res3 = client.post(
        "/api/v1/sales/trial/signup",
        json={"name": "David Kim", "email": "david@kimtalent.com", "company": "Kim Talent", "plan": "GROWTH_199"},
    )
    assert res3.status_code == 200
    assert res3.json()["status"] == "SUCCESS"

    # 4. Pipeline Summary
    res4 = client.get("/api/v1/sales/pipeline")
    assert res4.status_code == 200
    assert "total_leads" in res4.json()

    # 5. SaaS Website HTML
    res5 = client.get("/saas-website")
    assert res5.status_code == 200
    assert "ZERO Recruit" in res5.text
