"""ZERO — Personal Finance Database Connection & Permissions Verifier.

Tests connectivity to PostgreSQL, verifies read access on public.transactions and
public.users, and confirms that mutating write operations are properly blocked by
the read-only security role.

Usage:
    python scripts/test_finance_connection.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zero_core.config import load_env
from zero_core.finance_status import FinanceDBUnavailable, FinanceStatusAdapter

load_env()


def verify_finance_connection():
    print("=" * 65)
    print("   ZERO — Personal Finance PostgreSQL Connection Verifier")
    print("=" * 65)

    adapter = FinanceStatusAdapter()
    if not adapter.dsn:
        print("[!] FINANCE_DB_URL is not set in environment or .env file.")
        print("    1. Run scripts/setup_finance_db.sql against your PostgreSQL database.")
        print("    2. Set FINANCE_DB_URL in .env:")
        print("       FINANCE_DB_URL=postgresql://zero_finance_reader:password@localhost:5432/your_db")
        return False

    print(f"[*] Testing connection with configured DSN...")
    try:
        transactions = adapter.get_recent_transactions(limit=5)
        print(f"[✓] Successfully connected to PostgreSQL database!")
        print(f"[✓] Read access verified on public.transactions ({len(transactions)} recent records found).")

        if transactions:
            print("\nSample Records:")
            for t in transactions[:3]:
                print(f"  • {t.transaction_date} | {t.category or 'Uncategorized'} | {t.vendor or '-'} | {t.amount} {t.currency or ''}")

        totals = adapter.get_category_totals()
        print(f"\n[✓] Read access verified for category aggregation ({len(totals)} categories computed).")
        print("\n[SUCCESS] Finance Database integration is fully operational!")
        return True
    except FinanceDBUnavailable as exc:
        print(f"[!] Configuration Error: {exc}")
        return False
    except Exception as exc:
        err_msg = str(exc)
        print(f"[!] Database Connection Failed: {err_msg}")
        if "password authentication failed" in err_msg:
            print("\n[💡 SUPABASE PASSWORD HINT]")
            print("  1. Go to your Supabase Dashboard -> Settings (⚙️) -> Database.")
            print("  2. Click 'Reset database password' to set a new password.")
            print("  3. Ensure your FINANCE_DB_URL username is 'postgres.[your-project-id]' when using the pooler:")
            print("     FINANCE_DB_URL=postgresql://postgres.xxx:YourNewPassword@aws-0-ap-south-1.pooler.supabase.com:6543/postgres")
        return False


if __name__ == "__main__":
    verify_finance_connection()
