"""The agent's tools. Exactly three, allowlisted, each with a strict
pydantic argument schema:

- ``sql_query``     — read-only SQL over the local database. SELECT-only
  is enforced in code (writes, DDL, and multi-statements are rejected)
  *and* the connection itself is opened read-only.
- ``doc_search``    — keyword search over the policy documents in ``docs/``.
- ``account_stats`` — precomputed aggregates for one account.

There is deliberately no tool that can move money, close an alert, or
send a message: the agent can only gather evidence and draft.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


class ToolError(Exception):
    """Raised when a tool call is invalid or blocked by a guardrail."""


# --------------------------------------------------------------------------
# sql_query — SELECT-only enforcement
# --------------------------------------------------------------------------

_FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
    "PRAGMA", "ATTACH", "DETACH", "VACUUM", "GRANT", "REVOKE", "TRUNCATE",
}


def validate_select_only(sql: str) -> str:
    """Return the cleaned query if it is a single read-only SELECT.

    Raises :class:`ToolError` otherwise. The check is intentionally
    strict: forbidden keywords are rejected even inside string literals.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ToolError("Query must be a non-empty string.")
    body = sql.strip()
    if body.endswith(";"):
        body = body[:-1].strip()
    if ";" in body:
        raise ToolError("Multiple statements are not allowed.")
    # Strip leading SQL comments so they cannot smuggle a statement past.
    while True:
        if body.startswith("--"):
            body = body.split("\n", 1)[-1].strip()
        elif body.startswith("/*"):
            end = body.find("*/")
            if end == -1:
                raise ToolError("Unterminated comment in query.")
            body = body[end + 2:].strip()
        else:
            break
    first = re.match(r"[A-Za-z]+", body)
    if not first or first.group(0).upper() not in {"SELECT", "WITH"}:
        raise ToolError("Only SELECT queries are allowed.")
    words = set(re.findall(r"[A-Za-z]+", body.upper()))
    bad = words & _FORBIDDEN_KEYWORDS
    if bad:
        raise ToolError(f"Forbidden keyword(s) in query: {', '.join(sorted(bad))}.")
    if "INTO" in words:
        raise ToolError("SELECT ... INTO is not allowed.")
    return body


def _ro_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sql_query(db_path: Path, query: str, max_rows: int = 50) -> dict:
    sql = validate_select_only(query)
    conn = _ro_connect(db_path)
    try:
        rows = [dict(r) for r in conn.execute(sql).fetchmany(max_rows)]
    except sqlite3.Error as exc:
        raise ToolError(f"SQL error: {exc}") from exc
    finally:
        conn.close()
    return {"rows": rows, "row_count": len(rows), "truncated": len(rows) == max_rows}


# --------------------------------------------------------------------------
# doc_search — keyword search over docs/
# --------------------------------------------------------------------------

def _snippet(text: str, keywords: list[str], width: int = 240) -> str:
    low = text.lower()
    positions = [low.find(k) for k in keywords if low.find(k) >= 0]
    start = max(0, (min(positions) if positions else 0) - 60)
    snippet = re.sub(r"\s+", " ", text[start:start + width]).strip()
    if start > 0:
        snippet = "…" + snippet
    return snippet


def doc_search(docs_dir: Path, query: str, max_results: int = 3) -> dict:
    keywords = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    if not keywords:
        raise ToolError("Search query needs at least one keyword longer than 2 characters.")
    results = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        score = sum(low.count(k) for k in keywords)
        if score == 0:
            continue
        results.append({
            "file": path.name,
            "score": score,
            "content": text,
            "snippet": _snippet(text, keywords),
        })
    results.sort(key=lambda r: (-r["score"], r["file"]))
    return {"results": results[:max_results], "total_matches": len(results)}


# --------------------------------------------------------------------------
# account_stats — aggregates for one account
# --------------------------------------------------------------------------

def account_stats(db_path: Path, account_id: str) -> dict:
    conn = _ro_connect(db_path)
    try:
        account = conn.execute(
            "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        if account is None:
            raise ToolError(f"Unknown account: {account_id}")
        agg = conn.execute(
            """
            SELECT COUNT(*) AS txn_count,
                   COALESCE(SUM(amount), 0) AS total_amount,
                   COALESCE(AVG(amount), 0) AS avg_amount,
                   COALESCE(MAX(amount), 0) AS max_amount,
                   COUNT(DISTINCT merchant) AS distinct_merchants,
                   MIN(ts) AS first_txn,
                   MAX(ts) AS last_txn
            FROM transactions WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()
        alert_count = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE account_id = ?", (account_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    stats = dict(agg)
    stats["account_id"] = account_id
    stats["holder"] = account["holder"]
    stats["total_amount"] = round(stats["total_amount"], 2)
    stats["avg_amount"] = round(stats["avg_amount"], 2)
    stats["alert_count"] = alert_count
    return stats


# --------------------------------------------------------------------------
# Registry with strict argument schemas
# --------------------------------------------------------------------------

class SqlQueryArgs(BaseModel):
    query: str


class DocSearchArgs(BaseModel):
    query: str
    max_results: int = 3


class AccountStatsArgs(BaseModel):
    account_id: str


@dataclass
class ToolContext:
    db_path: Path
    docs_dir: Path


@dataclass
class _ToolSpec:
    args_model: type[BaseModel]
    fn: Callable[[ToolContext, BaseModel], dict]
    description: str


TOOLS: dict[str, _ToolSpec] = {
    "sql_query": _ToolSpec(
        SqlQueryArgs,
        lambda ctx, a: sql_query(ctx.db_path, a.query),
        "Read-only SQL (SELECT only) over tables: accounts, transactions, alerts.",
    ),
    "doc_search": _ToolSpec(
        DocSearchArgs,
        lambda ctx, a: doc_search(ctx.docs_dir, a.query, a.max_results),
        "Keyword search over internal policy documents.",
    ),
    "account_stats": _ToolSpec(
        AccountStatsArgs,
        lambda ctx, a: account_stats(ctx.db_path, a.account_id),
        "Aggregates for one account: counts, totals, average/max amount, merchants, alerts.",
    ),
}

ALLOWED_TOOLS = sorted(TOOLS)


def tool_descriptions() -> str:
    lines = []
    for name, spec in TOOLS.items():
        schema = json.dumps(spec.args_model.model_json_schema().get("properties", {}))
        lines.append(f"- {name}: {spec.description} Args schema: {schema}")
    return "\n".join(lines)


def run_tool(name: str, args: dict[str, Any] | None, ctx: ToolContext) -> dict:
    """Validate and execute one tool call. Raises ToolError if blocked."""
    if name not in TOOLS:
        raise ToolError(f"Unknown tool '{name}'. Allowed tools: {', '.join(ALLOWED_TOOLS)}.")
    spec = TOOLS[name]
    try:
        parsed = spec.args_model(**(args or {}))
    except ValidationError as exc:
        raise ToolError(f"Invalid arguments for {name}: {exc}") from exc
    return spec.fn(ctx, parsed)
