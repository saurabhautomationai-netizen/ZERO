"""Database Audit Specialist Worker for ZERO Engineering Organization.

Performs strictly READ-ONLY reverse-engineering, inspection, and auditing of
SQL schema files, DDL definitions, tables, indexes, constraints, and relational models.
Enforces execution guardrails preventing live database mutations or migrations.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from zero_core.engineering.discovery.policy import ReadOnlyPolicyEnforcer
from zero_core.engineering.workers.base import (
    EngineeringWorker,
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
    WorkerType,
)

logger = logging.getLogger("zero.engineering.workers.database_audit")


class DatabaseAuditWorker(EngineeringWorker):
    """Specialist worker for auditing SQL DDL and relational models in READ-ONLY mode."""

    def __init__(self):
        super().__init__(
            worker_id="worker_database_audit",
            name="Database Schema & DDL Audit Specialist",
            worker_type=WorkerType.NATIVE,
            capabilities=[
                WorkerCapability.DATABASE,
            ],
            risk_level="LOW",
            transport="IN_PROCESS_CALL",
        )
        self.enforcer = ReadOnlyPolicyEnforcer()

    def health_check(self) -> WorkerStatus:
        return WorkerStatus.AVAILABLE

    def run_task(self, context: ProjectContextPackage) -> WorkerResult:
        """Audits SQL schema definitions in context strictly in read-only mode."""
        self.enforcer.verify_action_allowed("audit_database_schemas")

        tables_found: Dict[str, Dict[str, Any]] = {}
        indexes_found: List[str] = []
        triggers_found: List[str] = []
        views_found: List[str] = []
        sql_files: List[str] = []

        table_regex = re.compile(r'(?i)create\s+table(?:\s+if\s+not\s+exists)?\s+([a-zA-Z0-9_\."]+)\s*\(([\s\S]*?)\);', re.MULTILINE)
        index_regex = re.compile(r'(?i)create\s+(?:unique\s+)?index(?:\s+if\s+not\s+exists)?\s+([a-zA-Z0-9_\."]+)', re.MULTILINE)
        trigger_regex = re.compile(r'(?i)create\s+trigger\s+([a-zA-Z0-9_\."]+)', re.MULTILINE)
        view_regex = re.compile(r'(?i)create\s+(?:or\s+replace\s+)?view\s+([a-zA-Z0-9_\."]+)', re.MULTILINE)

        for rel_path, content in context.relevant_files.items():
            if not rel_path.endswith((".sql", ".prisma")):
                continue
            sql_files.append(rel_path)

            # Extract tables
            for match in table_regex.finditer(content):
                tbl_raw = match.group(1).strip('"')
                tbl_name = tbl_raw.split(".")[-1].strip('"')
                body = match.group(2)
                cols = [line.strip().split()[0] for line in body.splitlines() if line.strip() and not line.strip().upper().startswith(("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "--"))]
                tables_found[tbl_name] = {
                    "source_file": rel_path,
                    "columns": cols[:8],
                    "column_count": len(cols),
                }

            # Extract indexes
            for match in index_regex.finditer(content):
                idx_name = match.group(1).split(".")[-1].strip('"')
                indexes_found.append(f"{idx_name} ({rel_path})")

            # Extract triggers
            for match in trigger_regex.finditer(content):
                trg_name = match.group(1).split(".")[-1].strip('"')
                triggers_found.append(f"{trg_name} ({rel_path})")

            # Extract views
            for match in view_regex.finditer(content):
                vw_name = match.group(1).split(".")[-1].strip('"')
                views_found.append(f"{vw_name} ({rel_path})")

        if tables_found:
            summary = (
                f"Discovered {len(tables_found)} relational table(s), {len(indexes_found)} index(es), "
                f"and {len(triggers_found)} trigger(s) across {len(sql_files)} SQL schema file(s)."
            )
            table_list_md = "\n".join(
                f"- **`{tname}`** ({tinfo['column_count']} columns, defined in `{tinfo['source_file']}`)"
                for tname, tinfo in tables_found.items()
            )
            analysis = (
                f"### Relational Model & Database Entities:\n{table_list_md}\n\n"
                f"- **Indexes Defined**: {len(indexes_found)}\n"
                f"- **Triggers Defined**: {len(triggers_found)}\n"
                f"- **Views Defined**: {len(views_found)}"
            )
        else:
            summary = "No SQL schema or DDL table definitions discovered in project context."
            analysis = "Scanned context files; no CREATE TABLE DDL schemas were detected."

        return WorkerResult(
            task_id=context.task_id,
            worker_id=self.worker_id,
            status="SUCCESS",
            summary=summary,
            analysis=analysis,
            project_id=context.project_id,
            files_read=sql_files,
            artifacts_created=list(tables_found.keys()),
            decisions={
                "table_count": str(len(tables_found)),
                "tables": ", ".join(tables_found.keys()),
                "index_count": str(len(indexes_found)),
                "trigger_count": str(len(triggers_found)),
            },
        )
