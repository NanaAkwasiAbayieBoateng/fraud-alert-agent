import json
from pathlib import Path

import pytest

from agent_app import db
from agent_app.graph import AgentConfig, Investigation
from agent_app.llm import ScriptedFakeLLM
from agent_app.trace import Tracer

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def tool_json(tool, args):
    return json.dumps({"action": "tool", "tool": tool, "args": args})


def finish_json(summary):
    return json.dumps({"action": "finish", "summary": summary})


@pytest.fixture()
def db_path(tmp_path):
    return db.seed(tmp_path / "test.db")


def make_investigation(db_path, responses, **config_overrides):
    config = AgentConfig(db_path=db_path, docs_dir=DOCS_DIR, **config_overrides)
    tracer = Tracer()
    llm = ScriptedFakeLLM(responses)
    return Investigation(llm, config, tracer=tracer), tracer


def test_full_scripted_investigation_then_approval(db_path):
    responses = [
        "Plan: inspect the flagged transaction, compare with the account baseline, check policy.",
        tool_json("sql_query", {
            "query": "SELECT txn_id, amount, merchant, ts FROM transactions "
                     "WHERE account_id = 'ACC-1001' ORDER BY ts DESC LIMIT 5",
        }),
        tool_json("account_stats", {"account_id": "ACC-1001"}),
        tool_json("doc_search", {"query": "high value new merchant review policy"}),
        finish_json(
            "Alert A1: a $2,450 ElectroWorld Online purchase at 03:12 is roughly 25x the "
            "account's average transaction, at a first-time merchant, preceded by two $1.00 "
            "and $1.50 test charges — matching the card-testing pattern in the high-value "
            "review policy. Recommend: hold pending customer contact."
        ),
    ]
    investigation, tracer = make_investigation(db_path, responses)

    result = investigation.run("A1")

    assert result["status"] == "awaiting_approval"
    assert result["filed"] is False
    assert "ElectroWorld" in result["draft"]
    assert result["steps"] == 3

    tools_called = [e["tool"] for e in tracer.events_of("tool_call")]
    assert tools_called == ["sql_query", "account_stats", "doc_search"]
    assert tracer.events_of("llm_call"), "every LLM call must be traced"
    assert tracer.events_of("draft_ready")

    # PII from the transaction memo must never reach the trace in clear text.
    serialized = json.dumps(tracer.events)
    assert "jordan.miles@example.com" not in serialized
    assert "4111 1111" not in serialized
    assert "[EMAIL]" in serialized

    # Nothing is filed until the human approves.
    assert db.get_alert(db_path, "A1")["status"] == "open"
    approved = investigation.approve()
    assert approved["filed"] is True
    assert db.get_alert(db_path, "A1")["status"] == "filed"


def test_approve_before_run_raises(db_path):
    investigation, _ = make_investigation(db_path, [])
    with pytest.raises(RuntimeError):
        investigation.approve()


def test_rejection_leaves_alert_open(db_path):
    responses = ["Plan: quick look.", finish_json("Draft summary for A2.")]
    investigation, _ = make_investigation(db_path, responses)
    result = investigation.run("A2")
    assert result["status"] == "awaiting_approval"
    rejected = investigation.reject(reason="needs more evidence")
    assert rejected["status"] == "rejected"
    assert db.get_alert(db_path, "A2")["status"] == "open"


def test_step_cap_stops_a_looping_llm(db_path):
    loop_forever = lambda messages: tool_json(  # noqa: E731
        "account_stats", {"account_id": "ACC-1001"}
    )
    responses = ["Plan: loop."] + [loop_forever] * 10
    investigation, tracer = make_investigation(db_path, responses, max_steps=3)

    result = investigation.run("A1")

    assert result["status"] == "gave_up"
    assert result["steps"] == 3
    assert "step cap" in result["error"]
    assert result["filed"] is False
    assert tracer.events_of("gave_up")
    with pytest.raises(RuntimeError):
        investigation.approve()


def test_spend_cap_stops_the_run(db_path):
    responses = ["A very thorough plan that uses up the entire token budget in one go."]
    investigation, _ = make_investigation(db_path, responses, max_tokens=1)

    result = investigation.run("A1")

    assert result["status"] == "gave_up"
    assert "spend cap" in result["error"]


def test_prompt_injection_in_document_is_not_followed(db_path):
    """The customer message attached to A1 instructs the agent to transfer
    money and close the alert. Even if the model tries to comply, the tool
    allowlist blocks it, the attempt is traced, and nothing changes."""
    responses = [
        "Plan: read the customer message, then check the account.",
        tool_json("doc_search", {"query": "customer message transfer funds alert", "max_results": 4}),
        # Simulated worst case: the model obeys the injected instruction.
        tool_json("transfer_funds", {"amount": 2450, "to": "ACC-9999"}),
        finish_json(
            "Alert A1: the attached customer message contains an instruction to move "
            "money and close the alert — treated as a red flag, not followed. The "
            "underlying $2,450 charge still needs human review."
        ),
    ]
    investigation, tracer = make_investigation(db_path, responses)
    txns_before = db.get_alert(db_path, "A1")

    result = investigation.run("A1")

    assert result["status"] == "awaiting_approval"
    assert result["filed"] is False

    # The injection was flagged by the guardrail when the doc was retrieved.
    guardrail_events = tracer.events_of("guardrail")
    assert guardrail_events and guardrail_events[0]["kind"] == "prompt_injection_flagged"
    assert "transfer_money" in guardrail_events[0]["signals"]

    # The disallowed tool call was attempted, blocked, and recorded — never executed.
    blocked = [
        e for e in tracer.events_of("tool_result")
        if e["tool"] == "transfer_funds"
    ]
    assert blocked and blocked[0]["ok"] is False
    assert "Unknown tool" in blocked[0]["error"]

    # No state changed: alert still open, no new transactions, draft carries no order.
    assert db.get_alert(db_path, "A1") == txns_before
    assert "transfer_funds" not in (result["draft"] or "")
