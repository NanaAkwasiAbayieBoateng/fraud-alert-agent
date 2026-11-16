import pytest

from agent_app import db
from agent_app.tools import ToolContext, ToolError, account_stats, doc_search, sql_query
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


@pytest.fixture()
def db_path(tmp_path):
    return db.seed(tmp_path / "test.db")


# --- SELECT-only enforcement -------------------------------------------------

def test_select_query_is_allowed(db_path):
    result = sql_query(db_path, "SELECT COUNT(*) AS n FROM transactions WHERE account_id = 'ACC-1001'")
    assert result["rows"][0]["n"] == 10


def test_select_with_trailing_semicolon_is_allowed(db_path):
    result = sql_query(db_path, "SELECT alert_id FROM alerts WHERE alert_id = 'A1';")
    assert result["rows"] == [{"alert_id": "A1"}]


@pytest.mark.parametrize(
    "bad_sql",
    [
        "INSERT INTO alerts VALUES ('A9', 'ACC-1001', 'TXN-9001', 'x', 'low', 'open', '2026-01-01')",
        "UPDATE alerts SET status = 'filed' WHERE alert_id = 'A1'",
        "DELETE FROM transactions WHERE txn_id = 'TXN-9001'",
        "DROP TABLE accounts",
        "ALTER TABLE accounts ADD COLUMN hacked TEXT",
        "CREATE TABLE pwned (x TEXT)",
        "REPLACE INTO alerts VALUES ('A1')",
        "PRAGMA table_info(alerts)",
        "SELECT 1; DROP TABLE accounts",
        "SELECT * FROM alerts; SELECT * FROM accounts",
        "WITH gone AS (DELETE FROM alerts RETURNING *) SELECT * FROM gone",
        "SELECT * INTO backup FROM alerts",
    ],
)
def test_writes_and_multi_statements_are_rejected(db_path, bad_sql):
    with pytest.raises(ToolError):
        sql_query(db_path, bad_sql)


def test_database_is_unchanged_after_rejected_writes(db_path):
    for bad in ("DELETE FROM alerts", "DROP TABLE alerts"):
        with pytest.raises(ToolError):
            sql_query(db_path, bad)
    result = sql_query(db_path, "SELECT COUNT(*) AS n FROM alerts")
    assert result["rows"][0]["n"] == 3


# --- account_stats -------------------------------------------------------------

def test_account_stats_for_demo_account(db_path):
    stats = account_stats(db_path, "ACC-1001")
    assert stats["txn_count"] == 10
    assert stats["max_amount"] == 2450.00
    assert stats["alert_count"] == 1
    assert stats["holder"] == "Jordan Miles"
    assert stats["distinct_merchants"] >= 6


def test_account_stats_unknown_account(db_path):
    with pytest.raises(ToolError):
        account_stats(db_path, "ACC-9999")


# --- doc_search ------------------------------------------------------------------

def test_doc_search_finds_triage_guide():
    result = doc_search(DOCS_DIR, "alert triage evidence baseline")
    files = [r["file"] for r in result["results"]]
    assert "alert_triage_guide.md" in files


def test_doc_search_finds_high_value_policy():
    result = doc_search(DOCS_DIR, "high value transaction five times average merchant")
    files = [r["file"] for r in result["results"]]
    assert files[0] == "high_value_transaction_review.md"


def test_tool_context_registry_rejects_unknown_tool(db_path):
    from agent_app.tools import run_tool

    ctx = ToolContext(db_path=db_path, docs_dir=DOCS_DIR)
    with pytest.raises(ToolError):
        run_tool("transfer_funds", {"amount": 2450, "to": "ACC-9999"}, ctx)
