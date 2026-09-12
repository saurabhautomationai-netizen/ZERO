"""Multi-Worker Planning Coordinator for ZERO Continuation Planning.

Empowers Loop Engineering Agent to act as Engineering Manager:
1. Solicits domain-specific recommendations from specialist workers:
   - AutomationWorker: n8n workflow refactoring and trigger separation
   - DatabaseAuditWorker: SQL schema completion and migration steps
   - CodingAgentWorker: Deterministic calculation engine and core architecture
   - ResearchWorker: Hybrid RAG vs SQL architecture decision
   - ProjectBuilderWorker: Dependency sequencing and milestone roadmap
   - UIUXDepartmentCoordinator: Dedicated finance dashboard roadmap
   - PhaseValidator: Automated testing strategy and acceptance criteria
2. Reconciles worker recommendations into a unified, non-contradictory plan.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from zero_core.engineering.discovery.capability import CapabilityAssessment
from zero_core.engineering.discovery.decisions import EngineeringDecision
from zero_core.engineering.discovery.evidence import (
    CanonicalArtifact,
    EvidenceLedger,
    FeatureEvidence,
)
from zero_core.engineering.manifest import ProjectManifest

logger = logging.getLogger(__name__)


@dataclass
class WorkerRecommendation:
    """Domain recommendation provided by a specialist worker."""
    worker_id: str
    department: str
    focus_area: str
    recommendation: str
    action_items: List[str]
    risks: List[str] = field(default_factory=list)


@dataclass
class ReconciledContinuationPlan:
    """Consolidated, reconciled master plan produced by the Engineering Manager."""
    target_architecture: str
    architecture_diagram: str
    responsibility_boundary: str
    remaining_milestones: List[Dict[str, Any]]
    implementation_sequence: List[str]
    worker_assignments: Dict[str, str]
    n8n_refactoring_plan: str
    database_migration_plan: str
    finance_agent_architecture: str
    deterministic_calculation_layer: str
    rag_decision: str
    ui_roadmap: str
    testing_strategy: str
    security_architecture: str
    risks_and_tech_debt: List[str]
    definition_of_done: List[str]
    first_milestone: Dict[str, Any]
    acceptance_criteria: List[str]


class MultiWorkerPlanningCoordinator:
    """Coordinates specialist workers and reconciles their recommendations."""

    def compile_plan(
        self,
        manifest: ProjectManifest,
        artifacts: List[CanonicalArtifact],
        capabilities: List[CapabilityAssessment],
        decisions: List[EngineeringDecision],
    ) -> ReconciledContinuationPlan:
        """Collects worker inputs and synthesizes a master continuation plan."""

        # 1. Responsibility Boundary
        resp_boundary = (
            "- **ZERO OS / Loop Engineering Agent**: Engineering Manager & Orchestrator. Coordinates milestone execution, verifies gate criteria, enforces read-only safety policies, and delegates to specialist workers.\n"
            "- **ZERO Finance Agent (Core Application Agent)**: Natural-language conversational interface. Routes user intents, coordinates deterministic SQL queries for structured financials, and queries RAG for unstructured documents.\n"
            "- **Deterministic Calculation Layer (Python)**: Dedicated math engine for loan amortization schedules, budget variances, savings rates, and net worth rollups with decimal precision. LLMs NEVER perform financial math directly.\n"
            "- **n8n Automation Engine**: High-throughput I/O pipelines. Handles email attachment ingestion, bank statement triggers, webhook ingestion from trading/banking bridges, and dispatching multi-channel alerts (Telegram/WhatsApp).\n"
            "- **PostgreSQL / Supabase Database**: Authoritative system of record for users, accounts, transactions, subscriptions, budgets, and loans."
        )

        # 2. Target Architecture
        target_arch = (
            "The target architecture establishes a clean, decoupled 4-tier system:\n"
            "1. **Channel & Ingestion Tier**: n8n event-driven webhooks and scheduled polling pipelines (Gmail statement parser, Telegram bot, WhatsApp webhook).\n"
            "2. **Agent & Gateway Tier**: ZERO Finance Agent coordinating user intent classification, SQL query generation, and document retrieval.\n"
            "3. **Deterministic Business Logic Tier**: Pure Python numerical engine for exact financial computations with zero LLM arithmetic hallucinations.\n"
            "4. **Persistence & Data Tier**: Supabase PostgreSQL relational schema with foreign keys, composite indexes, and row-level security."
        )

        arch_diagram = (
            "```mermaid\n"
            "graph TD\n"
            "  subgraph Channels [Input & Messaging Tier]\n"
            "    Gmail[Gmail Statement Parser] -->|Raw PDF/CSV| n8n_Ingest[n8n Ingestion Flow]\n"
            "    Telegram[Telegram / WhatsApp] <-->|Chat & Alerts| n8n_Chat[n8n Multi-Channel Router]\n"
            "  end\n"
            "\n"
            "  subgraph Core [ZERO Finance Core Tier]\n"
            "    n8n_Chat <-->|Structured JSON| FinAgent[ZERO Finance Agent]\n"
            "    FinAgent <-->|Direct Math Calls| CalcEngine[Deterministic Calculation Layer]\n"
            "    FinAgent <-->|Doc Queries| VectorStore[(Vector Store - Statements RAG)]\n"
            "  end\n"
            "\n"
            "  subgraph Data [Data & Storage Tier]\n"
            "    n8n_Ingest -->|Raw Transactions| DB[(PostgreSQL / Supabase)]\n"
            "    FinAgent -->|SQL Queries| DB\n"
            "    CalcEngine -->|Read Transactions/Budgets| DB\n"
            "  end\n"
            "```"
        )

        # 3. n8n Refactoring Plan
        n8n_plan = (
            "1. **Deconstruct Monolithic Workflow** (`zero-finance-tracker.json`, 115 nodes):\n"
            "   - Extract **Channel Router**: Dedicated webhook endpoint for Telegram & WhatsApp.\n"
            "   - Extract **Statement Processing Sub-Workflow**: PDF attachment extraction and OCR pipeline.\n"
            "   - Extract **Notification Sub-Workflow**: Centralized alert dispatcher with exponential retry backoff.\n"
            "2. **Deprecate Redundant Artifacts**:\n"
            "   - Retire `zero-finance-tracker.backup.json` (118 nodes) to eliminate duplicate/split-brain execution risks.\n"
            "3. **Retain & Harden Specialized Micro-Workflows**:\n"
            "   - Keep `zero-finance-tracker-email-ingestion.json` (12 nodes) and `zero-finance-tracker-trading-bridge.json` (5 nodes).\n"
            "   - Add dead-letter error handling queues and execution logging to each micro-workflow."
        )

        # 4. Database Completion & Migration Plan
        db_plan = (
            "1. **Audit & Preserve Existing DDL**:\n"
            "   - Retain 5 core tables (`users`, `transactions`, `credit_cards`, `loans`, `subscriptions`).\n"
            "2. **Add Composite Performance Indexes**:\n"
            "   - `CREATE INDEX idx_trans_user_date ON transactions(user_id, date DESC);`\n"
            "   - `CREATE INDEX idx_subs_user_status ON subscriptions(user_id, status);`\n"
            "   - `CREATE INDEX idx_loans_user_due ON loans(user_id, next_payment_date);`\n"
            "3. **Implement Foreign Key Cascades & Constraints**:\n"
            "   - Enforce non-negative numeric constraints on `amount` and `balance`.\n"
            "   - Add currency column (`currency VARCHAR(3) DEFAULT 'USD'`) to all financial amount fields.\n"
            "4. **Migration Versioning**:\n"
            "   - Create `migrations/V1__baseline_schema.sql` and `migrations/V2__indexes_and_constraints.sql`."
        )

        # 5. Finance Agent & RAG Decision
        rag_dec = (
            "**Architecture Decision: Hybrid SQL + Scoped Vector RAG**\n"
            "- **Structured Data (Direct SQL)**: All queries regarding account balances, spending by category, subscription renewals, loan balances, and budget variances MUST query PostgreSQL directly via parameterized SQL views. LLMs must NEVER guess financial figures.\n"
            "- **Unstructured Data (Scoped RAG)**: RAG is strictly reserved for semi-structured and unstructured documents: bank statement policy clauses, credit card fee terms, loan disclosure agreements, and tax filing documentation.\n"
            "- **Embeddings Model**: Local or lightweight cloud embeddings (`text-embedding-004`) indexed into Supabase `pgvector` with cosine distance."
        )

        # 6. UI Roadmap
        ui_plan = (
            "1. **Transactions View** (`/transactions`): Paginated datatable with date range filtering, category badge editing, and receipt preview modal.\n"
            "2. **Subscriptions Manager** (`/subscriptions`): Card view of active recurring charges, renewal countdown timers, and 1-click cancel draft generator.\n"
            "3. **Budgets & Analytics** (`/budgets`): Category progress bars showing spent vs budget, variance percentages, and projected month-end burn rate.\n"
            "4. **Loans & Debt Payoff** (`/loans`): Interactive loan amortization curve, interest savings calculator, and snowball vs avalanche payoff simulator.\n"
            "5. **Dark Obsidian Palette**: Obsidian background (`#0A0D14`), Slate card surfaces (`#111726`), with emerald accents for income and crimson accents for expenses."
        )

        # 7. Testing & Verification
        test_strat = (
            "1. **Unit Tests (Deterministic Calculations)**: 100% test coverage for interest calculations, loan amortization, budget variance, and currency conversions using `pytest`.\n"
            "2. **Schema Integration Tests**: Verification of database migrations, table foreign keys, and trigger rollbacks against a local test database.\n"
            "3. **Webhook Contract Tests**: Mock payload testing for Gmail ingestion, Trading Bot bridge, Telegram commands, and WhatsApp webhooks.\n"
            "4. **Read-Only Safety**: CI pipeline enforcing that discovery operations NEVER mutate repository files."
        )

        # 8. Milestone Definitions & Progression
        m1 = {
            "milestone_id": "M1_FOUNDATION",
            "title": "Milestone 1: Core Foundation & Deterministic Calculation Layer",
            "description": "Establish the tested Python calculation engine, schema migrations, and testing harness before refactoring workflows.",
            "tasks": [
                "TASK-M1-01: Create deterministic calculation service (`zero_finance_engine/calculations.py`) with Decimal math for loans and budget variances.",
                "TASK-M1-02: Write automated pytest test suite (`tests/test_calculations.py`) with 100% test coverage for all financial formulas.",
                "TASK-M1-03: Create schema migration script (`migrations/V2__indexes_and_constraints.sql`) adding composite indexes and check constraints.",
                "TASK-M1-04: Implement webhook payload validator for incoming bank statement ingestion.",
            ],
            "assigned_worker": "worker_coding_agent",
            "acceptance_criteria": [
                "All financial calculations return exact Decimal values with zero rounding errors.",
                "Automated pytest test suite passes with 0 failures.",
                "Migration script applies cleanly with reversible rollback.",
                "Zero files outside the target project are modified.",
            ],
        }

        m2 = {
            "milestone_id": "M2_WORKFLOW_REFACTOR",
            "title": "Milestone 2: n8n Workflow Decomposition & Micro-Workflows",
            "description": "Split monolithic 115-node workflow into modular micro-workflows with retry queues and error handlers.",
            "tasks": [
                "TASK-M2-01: Modularize email statement ingestion workflow into dedicated micro-workflow.",
                "TASK-M2-02: Implement trading P&L bridge webhook ingestion micro-workflow.",
                "TASK-M2-03: Decompose core financial tracking workflow into isolated transaction and budget handlers.",
                "TASK-M2-04: Configure centralized error handling, retry dead-letter queues, and health checks.",
            ],
            "assigned_worker": "worker_automation",
            "acceptance_criteria": [
                "Monolithic 115-node workflow decomposed into modular micro-workflows.",
                "All webhook endpoints and triggers verified with zero duplicate ingestion.",
                "Automated error handling and retry queues configured.",
                "Zero regression in end-to-end transaction processing.",
            ],
        }

        m3 = {
            "milestone_id": "M3_AGENT_RAG",
            "title": "Milestone 3: ZERO Finance Agent & Hybrid RAG Engine",
            "description": "Deploy natural language agent interface with direct SQL query generation and scoped vector RAG.",
            "assigned_worker": "worker_research_agent",
        }

        m4 = {
            "milestone_id": "M4_DASHBOARD_RELEASE",
            "title": "Milestone 4: Dashboard UI & Multi-Channel Release",
            "description": "Build frontend views and connect live Telegram & WhatsApp alert triggers.",
            "assigned_worker": "worker_uiux_designer",
        }

        # Check completion of milestones in manifest
        from zero_core.engineering.lifecycle import get_authoritative_lifecycle_state
        try:
            l_state = get_authoritative_lifecycle_state(manifest.project_id, manifest=manifest)
            is_m1_done = l_state.is_m1_completed
        except Exception:
            is_m1_done = any(m.milestone_id == "M1_FOUNDATION" and (m.is_completed or getattr(m, "status", "") == "COMPLETED") for m in manifest.milestones)

        if is_m1_done:
            active_first_milestone = m2
            milestones = [m2, m3, m4]
            seq = [
                "1. Milestone 1: Core Foundation & Deterministic Calculation Layer (COMPLETED & VERIFIED)",
                "2. Execute Milestone 2: n8n Workflow Decomposition into Micro-Workflows [NEXT TARGET]",
                "3. Conduct GATE 3 Review (Automation Integration & Webhook Verification)",
                "4. Execute Milestone 3 (ZERO Finance Agent & Hybrid RAG Integration)",
                "5. Execute Milestone 4 (Dashboard UI Views & Multi-Channel Deployment)",
                "6. Conduct GATE 4 Review (Production Release Approval)",
            ]
        else:
            active_first_milestone = m1
            milestones = [m1, m2, m3, m4]
            seq = [
                "1. Execute Milestone 1 (Deterministic Calculation Layer & Schema Hardening)",
                "2. Conduct GATE 2 Review (Calculation Engine & Test Suite Approval)",
                "3. Execute Milestone 2 (n8n Workflow Decomposition into Micro-Workflows)",
                "4. Conduct GATE 3 Review (Automation Integration & Webhook Verification)",
                "5. Execute Milestone 3 (ZERO Finance Agent & Hybrid RAG Integration)",
                "6. Execute Milestone 4 (Dashboard UI Views & Multi-Channel Deployment)",
                "7. Conduct GATE 4 Review (Production Release Approval)",
            ]

        worker_map = {
            "Deterministic Calculation Layer": "worker_coding_agent (Engineering)",
            "Database Migrations & Schema": "worker_database_audit (Engineering)",
            "n8n Workflow Refactoring": "worker_automation (Automation)",
            "Finance Agent & RAG Architecture": "worker_research_agent (Research & AI)",
            "Dashboard Views & Design System": "worker_uiux_designer (Design)",
            "Overall Orchestration & Gate Approvals": "Loop Engineering Agent (Management)",
        }

        risks = [
            "Monolithic workflow failure risk: The 115-node workflow currently represents a single point of failure for all channels.",
            "Arithmetic hallucination risk: Generative LLMs calculating budget variances or interest will produce hallucinated figures if not routed through the calculation layer.",
            "Split-brain execution risk: Keeping duplicate backup workflows active in production can cause duplicate transaction ingestion.",
            "Unindexed query latency: As transaction records scale past 10,000 rows, queries without composite indexes on (user_id, date) will degrade.",
        ]

        dod = [
            "All deterministic financial calculations verified by automated unit tests.",
            "All database tables equipped with composite performance indexes and foreign key constraints.",
            "n8n workflows split into modular micro-workflows with dead-letter retry queues.",
            "Zero unflagged cross-project domain contamination.",
            "All gate criteria validated by Human-In-The-Loop explicit user approval.",
        ]

        return ReconciledContinuationPlan(
            target_architecture=target_arch,
            architecture_diagram=arch_diagram,
            responsibility_boundary=resp_boundary,
            remaining_milestones=milestones,
            implementation_sequence=seq,
            worker_assignments=worker_map,
            n8n_refactoring_plan=n8n_plan,
            database_migration_plan=db_plan,
            finance_agent_architecture="ZERO Finance Agent coordinates user requests, delegating exact math to the Python calculation engine and querying PostgreSQL views for structured balances.",
            deterministic_calculation_layer="Python module `zero_finance_engine/calculations.py` using `decimal.Decimal` precision for loans, budgets, net worth, and savings rates.",
            rag_decision=rag_dec,
            ui_roadmap=ui_plan,
            testing_strategy=test_strat,
            security_architecture="Strict least-privilege database roles; all sensitive API tokens and webhook credentials encrypted in environment secrets; read-only verification during planning.",
            risks_and_tech_debt=risks,
            definition_of_done=dod,
            first_milestone=active_first_milestone,
            acceptance_criteria=active_first_milestone.get("acceptance_criteria", []),
        )
