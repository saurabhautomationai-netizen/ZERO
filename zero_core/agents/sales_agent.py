"""Sales & Growth Agent for Commercializing the HR Recruitment AI Assistant."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from zero_core.sales.crm import DEFAULT_SALES_CRM, SalesCRMStore, SalesLead, TrialSubscription


class SalesAgent:
    """Orchestrates commercial pipelines, social marketing content, demos, and trial onboarding."""

    def __init__(self, crm: Optional[SalesCRMStore] = None):
        self.crm = crm or DEFAULT_SALES_CRM

    def get_pipeline_summary(self) -> Dict[str, Any]:
        leads = self.crm.list_leads()
        trials = self.crm.list_trials()
        demos = self.crm.list_demos()

        return {
            "total_leads": len(leads),
            "active_30_day_trials": len([t for t in trials if t.is_active]),
            "scheduled_demos": len(demos),
            "converted_customers": len([t for t in trials if t.converted]),
            "pipeline_stages": {
                "NEW_LEAD": len([l for l in leads if l.status == "NEW_LEAD"]),
                "DEMO_BOOKED": len([l for l in leads if l.status == "DEMO_BOOKED"]),
                "TRIAL_ACTIVE": len([l for l in leads if l.status == "TRIAL_ACTIVE"]),
                "CONVERTED": len([l for l in leads if l.status == "CONVERTED"]),
            },
        }

    def generate_marketing_campaign(self, channel: str, focus_topic: str = "AI ATS vs Legacy Zoho") -> Dict[str, Any]:
        channel_lower = channel.lower()

        if "insta" in channel_lower:
            return {
                "channel": "Instagram",
                "format": "5-Slide Carousel & Reel Script",
                "headline": "Why Modern Recruiters Are Ditching 2015-Era Spreadsheets for AI ATS",
                "slides": [
                    {"slide": 1, "hook": "Stop wasting 4 hours a day manually reading resumes."},
                    {"slide": 2, "problem": "Legacy ATS tools charge $90/seat just to store PDFs like a filing cabinet."},
                    {"slide": 3, "solution": "Our AI Recruiter scores candidate ATS fit + technical gaps in 2 seconds."},
                    {"slide": 4, "feature_spotlight": "Live Dynamic Interview Copilot prompts you with the exact technical questions during calls."},
                    {"slide": 5, "cta": "Try it 100% free for 30 days (Link in Bio! No Credit Card Required)."},
                ],
                "caption": (
                    "Hiring top talent shouldn't feel like manual data entry. 🚀\n\n"
                    "With our Next-Gen AI Recruitment Assistant, you get:\n"
                    "✅ Automated Resume ATS Scoring\n"
                    "✅ Live Technical Interview Copilot\n"
                    "✅ WhatsApp & Email Candidate Outbox\n\n"
                    "👉 Start your 30-Day Free Trial today at the link in bio! #HRTech #RecruitmentAI #ATS #Staffing"
                ),
            }

        elif "link" in channel_lower:
            return {
                "channel": "LinkedIn",
                "format": "B2B Thought-Leadership & Product Teardown",
                "headline": "The Hidden Tax on Staffing Agencies: Why Per-Seat ATS Pricing Is Dead",
                "post_body": (
                    "If you run a recruitment agency with 10 headhunters, you're likely paying $6,000–$10,000 every single year for legacy ATS software.\n\n"
                    "The worst part? Most of those tools are just passive databases.\n\n"
                    "We built the HR Recruitment AI Assistant to change that:\n"
                    "1️⃣ Dynamic Candidate ATS Match: Automatically flags missing candidate skills before you pick up the phone.\n"
                    "2️⃣ Live Interview Copilot: Gives your recruiters tailored questions and evaluation rubrics on the fly.\n"
                    "3️⃣ 100% Private Cloud Ownership: Hosted securely on your own Supabase instance with zero per-seat fees.\n\n"
                    "Curious to see how it cuts hiring turnaround by 60%?\n\n"
                    "Comment 'DEMO' or claim your 30-day full access free trial below. 👇"
                ),
            }

        elif "what" in channel_lower:
            return {
                "channel": "WhatsApp",
                "format": "Interactive Quick-Start Template",
                "template_name": "hr_trial_welcome",
                "message": (
                    "👋 Hi {{1}}, welcome to the *HR Recruitment AI Assistant*!\n\n"
                    "Your 30-Day Free Trial workspace is ready.\n"
                    "Here is your instant access link: {{2}}\n\n"
                    "💡 *Quick Start Tip:* Import your job description and test the *AI Recruiter Chat* to find matching candidates in seconds.\n\n"
                    "Reply here if you would like a 10-minute guided live walkthrough!"
                ),
            }

        else:
            return {
                "channel": "Email Drip",
                "format": "Day 1 Welcome & Onboarding Guide",
                "subject": "Welcome to your 30-Day HR Recruitment AI Assistant Trial! 🚀",
                "body": (
                    "Hi there,\n\n"
                    "Welcome to your 30-Day Free Trial of the HR Recruitment AI Assistant!\n\n"
                    "Here's how to make the most of your first 24 hours:\n"
                    "1. Upload a batch of candidate resumes using our Bulk Import tool.\n"
                    "2. View your Executive KPI overview with real-time velocity curves.\n"
                    "3. Open the AI Interview Copilot to generate customized candidate question rubrics.\n\n"
                    "Need any help? Our team is always one message away.\n\n"
                    "Best regards,\nThe HR AI Assistant Team"
                ),
            }

    def generate_30_day_trial_sequence(self) -> List[Dict[str, Any]]:
        return [
            {"day": 1, "trigger": "Signup", "theme": "Welcome & Sample Candidate Import Walkthrough"},
            {"day": 7, "trigger": "Week 1", "theme": "AI Recruiter Semantic Chat Feature Highlight"},
            {"day": 14, "trigger": "Week 2", "theme": "Live Interview Copilot & Question Generator"},
            {"day": 25, "trigger": "5 Days Left", "theme": "Trial Expiry Alert + 20% Growth Plan Annual Discount"},
            {"day": 30, "trigger": "Last Day", "theme": "Final Plan Activation & Account Migration"},
        ]


DEFAULT_SALES_AGENT = SalesAgent()
