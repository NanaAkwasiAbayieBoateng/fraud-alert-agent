"""Guardrails: PII redaction and prompt-injection flagging.

- :func:`redact_pii` scrubs emails, payment-card numbers (Luhn-checked, so
  ordinary long numbers are left alone), and phone numbers from text before
  it is written to traces or fed back to the model.
- :func:`find_injection_signals` flags instruction-like text inside
  retrieved documents. Retrieved content is always treated as untrusted
  data by the agent; the flags exist so traces show the attempt.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
PHONE_RE = re.compile(r"\b(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}\b")

_INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ignore_instructions", re.compile(r"ignore (your|all|the) (previous|prior) instructions", re.I)),
    ("system_override", re.compile(r"system override", re.I)),
    ("disregard_rules", re.compile(r"disregard (your|the) (rules|instructions|safety)", re.I)),
    ("transfer_money", re.compile(r"transfer (the )?(funds|money|\$)", re.I)),
    ("mark_resolved", re.compile(r"mark this alert as (resolved|closed)", re.I)),
    ("hide_from_human", re.compile(r"do not (tell|inform|notify) the (analyst|user|human|reviewer)", re.I)),
]


def _luhn_ok(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact_pii(text: str) -> str:
    """Replace emails, valid card numbers, and phone numbers with markers."""
    if not text:
        return text
    text = EMAIL_RE.sub("[EMAIL]", text)

    def _card_sub(match: re.Match) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return "[CARD]"
        return raw

    text = CARD_CANDIDATE_RE.sub(_card_sub, text)
    text = PHONE_RE.sub("[PHONE]", text)
    return text


def find_injection_signals(text: str) -> list[str]:
    """Return labels of instruction-like patterns found in *text*."""
    if not text:
        return []
    return [label for label, pattern in _INJECTION_PATTERNS if pattern.search(text)]
