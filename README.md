# Fraud Alert Agent — LLM Agent with Tool Use

**Status:** Planned · **Roadmap stage:** Advanced (Project P4)
Part of the [ML / AI Engineer Roadmap](https://github.com/NanaAkwasiAbayieBoateng/ai-ml-engineer-roadmap) — full plan in the roadmap's [P4 deep-dive](https://github.com/NanaAkwasiAbayieBoateng/ai-ml-engineer-roadmap/blob/main/projects/p4-llm-agent.md).

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

## Stack

Python · LangGraph · FastAPI · Docker
