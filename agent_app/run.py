"""CLI: investigate one fraud alert with the local Ollama model.

    python -m agent_app.run --alert-id A1                # interactive approval
    python -m agent_app.run --alert-id A1 --auto-approve # demo mode

The agent drafts a case summary; nothing is filed until a human approves
(interactively, or via --auto-approve for demos).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

from . import db
from .graph import build_investigation
from .llm import OllamaChatClient
from .trace import Tracer

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Investigate a fraud alert with a local LLM agent.")
    parser.add_argument("--alert-id", default="A1", help="Alert to investigate (default: A1)")
    parser.add_argument("--db", default=str(db.default_db_path()), help="Path to the SQLite database")
    parser.add_argument("--docs", default=str(REPO_ROOT / "docs"), help="Path to the policy docs folder")
    parser.add_argument("--trace", default=None, help="Trace JSONL path (default: traces/<alert-id>.jsonl)")
    parser.add_argument("--auto-approve", action="store_true", help="Approve the draft without prompting (demos)")
    parser.add_argument("--max-steps", type=int, default=int(os.environ.get("AGENT_MAX_STEPS", "8")))
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("AGENT_MAX_TOKENS", "20000")))
    args = parser.parse_args(argv)

    db_path = db.ensure_db(args.db)
    trace_path = args.trace or f"traces/{args.alert_id}.jsonl"
    tracer = Tracer(trace_path)
    investigation = build_investigation(
        db_path=db_path,
        docs_dir=Path(args.docs),
        llm=OllamaChatClient(),
        tracer=tracer,
        max_steps=args.max_steps,
        max_tokens=args.max_tokens,
    )

    print(f"Investigating alert {args.alert_id} "
          f"(model: {investigation.llm.model} @ {investigation.llm.host}) ...")
    try:
        result = investigation.run(args.alert_id)
    except httpx.ConnectError:
        print(
            "\nCould not reach Ollama. Is it running? Start it with `ollama serve` "
            "and make sure the model is pulled: `ollama pull llama3.1:8b`.",
            file=sys.stderr,
        )
        return 2
    except ValueError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2

    print(f"\n--- Investigation plan ---\n{result['plan']}")
    print(f"\n--- Draft case summary (steps: {result['steps']}, tokens: {result['tokens_spent']}) ---")
    print(result["draft"])
    print(f"\nFull trace written to {trace_path}")

    if result["status"] == "gave_up":
        print("\nThe agent stopped before completing (see reason above). Nothing was filed.")
        return 1
    if result["status"] != "awaiting_approval":
        print(f"\nUnexpected status: {result['status']}. Nothing was filed.")
        return 1

    if args.auto_approve:
        investigation.approve()
        print("\nApproved (--auto-approve). Case filed.")
        return 0

    answer = input("\nApprove filing this case? [y/N] ").strip().lower()
    if answer in {"y", "yes"}:
        investigation.approve()
        print("Approved. Case filed.")
    else:
        investigation.reject(reason="rejected at CLI prompt")
        print("Rejected. Nothing was filed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
