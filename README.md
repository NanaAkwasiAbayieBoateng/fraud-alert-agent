# Fraud Alert Agent — LLM Agent with Tool Use

**Status:** Scaffold built — runnable · **Roadmap stage:** Advanced (Project P4)
Part of the [ML / AI Engineer Roadmap](https://github.com/NanaAkwasiAbayieBoateng/ai-ml-engineer-roadmap) — full plan in the roadmap's [P4 deep-dive](https://github.com/NanaAkwasiAbayieBoateng/ai-ml-engineer-roadmap/blob/main/projects/p4-llm-agent.md).

📖 New here? Read [BLOG_POST.md](BLOG_POST.md) — a file-by-file walkthrough of the whole project.

An agent that investigates a fraud alert — gathers evidence with real tools and drafts a case summary for human approval. Bounded job, done safely, with receipts.

## Plan

1. **The job:** given an alert, gather evidence and draft a case summary. One job, done well.
2. **Tools (at least 3),** each with a strict input schema: a read-only SQL tool over a transactions database, document search (from [fraud-docs-rag](https://github.com/NanaAkwasiAbayieBoateng/fraud-docs-rag)), and one external API or stats tool.
3. **Agent loop in LangGraph:** plan → call tools → observe → next step or finish. Hard caps on steps and spend per run.
4. **Error recovery:** retries with backoff, fallbacks when a tool returns nothing, and a defined "give up and say why" path.
5. **Guardrails:** SELECT-only enforcement, PII redaction, tool allowlist.
6. **Human-in-the-loop:** the agent drafts; a human approves before anything is filed or sent.
7. **Tracing:** every step logged — prompts, tool calls, results, latency, cost.
8. **Scenario tests:** 10 end-to-end scenarios including a prompt-injection attempt hidden in a retrieved document, which the agent must not follow.

## Done when

The agent passes the scenario set with full traces, the injection attempt is demonstrably blocked, and the approval step works.

## What's in the scaffold

- `agent_app/llm.py` — Ollama chat client (local, free) + a scripted fake LLM for tests.
- `agent_app/db.py` — SQLite demo database with deterministic synthetic accounts, transactions, and alerts (alert `A1` is the demo case).
- `agent_app/tools.py` — three allowlisted tools with strict schemas: `sql_query` (SELECT-only, enforced in code and via a read-only connection), `doc_search` (keyword search over `docs/`), `account_stats`.
- `agent_app/guardrails.py` — PII redaction (emails, Luhn-checked card numbers, phone numbers) and prompt-injection flagging.
- `agent_app/trace.py` — JSONL tracer: prompts, tool calls, results, and latency for every step, PII-redacted.
- `agent_app/graph.py` — LangGraph state graph: plan → tool loop with hard step and token-spend caps → draft case summary → human approval gate. Nothing is filed until `approve()` is called.
- `agent_app/run.py` — CLI entry point.
- `docs/` — three short policy documents plus a customer message containing a prompt-injection attempt, which the security test in `tests/test_agent.py` proves the agent does not follow.
- `tests/` — SELECT-only enforcement, PII redaction, step/spend caps, approval gating, a full scripted investigation, and the injection test. The suite runs **without Ollama** (scripted fake LLM).

## Setup

You need Python 3.11+ and [Ollama](https://ollama.com) installed and running (`ollama serve`). Everything is free and local — no API keys. Copy `.env.example` to `.env` if you want to change the model, host, or caps.

## Run commands

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies (free / open-source only)
pip install -r requirements.txt

# 3. Pull the local LLM (Ollama must be installed and running)
ollama pull llama3.1:8b

# 4. Seed the local demo database (synthetic data; safe to re-run)
python -m agent_app.db

# 5. Run an investigation — interactive approval
python -m agent_app.run --alert-id A1

# 6. Run an investigation — auto-approve (demo mode)
python -m agent_app.run --alert-id A1 --auto-approve

# 7. Run the test suite (no Ollama needed — tests use a scripted fake LLM)
pytest
```

The run prints the investigation plan and the draft case summary, writes a full JSONL trace to `traces/<alert-id>.jsonl`, and — in interactive mode — asks before filing anything. Alerts `A2` and `A3` are also seeded if you want to try other cases.

## Stack

Python · LangGraph · Ollama (local LLM) · SQLite · httpx · pydantic
