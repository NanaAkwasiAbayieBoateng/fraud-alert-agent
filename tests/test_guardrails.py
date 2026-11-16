from agent_app.guardrails import find_injection_signals, redact_pii
from agent_app.trace import Tracer


def test_email_is_redacted():
    assert redact_pii("contact jordan.miles@example.com today") == "contact [EMAIL] today"


def test_card_number_with_spaces_is_redacted():
    assert redact_pii("card 4111 1111 1111 1111 was used") == "card [CARD] was used"


def test_card_number_with_dashes_is_redacted():
    assert redact_pii("card 4111-1111-1111-1111 was used") == "card [CARD] was used"


def test_card_number_without_separators_is_redacted():
    assert redact_pii("card 4111111111111111 was used") == "card [CARD] was used"


def test_non_card_long_number_is_left_alone():
    # 16 digits, but fails the Luhn check — not a card number.
    assert redact_pii("reference 1234 5678 9012 3456") == "reference 1234 5678 9012 3456"


def test_amounts_and_dates_are_left_alone():
    text = "Charge of 2450.00 on 2026-11-14, order 12345678"
    assert redact_pii(text) == text


def test_phone_number_is_redacted():
    assert redact_pii("call 555-010-1234 now") == "call [PHONE] now"


def test_tracer_redacts_everything_it_records(tmp_path):
    tracer = Tracer(tmp_path / "trace.jsonl")
    tracer.record("note", text="paid with 4111 1111 1111 1111 by jordan.miles@example.com")
    serialized = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert "4111" not in serialized
    assert "jordan.miles@example.com" not in serialized
    assert "[CARD]" in serialized and "[EMAIL]" in serialized


def test_injection_signals_detected_in_customer_message():
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "docs" / "customer_message_A1.md").read_text(encoding="utf-8")
    signals = find_injection_signals(text)
    assert "ignore_instructions" in signals
    assert "transfer_money" in signals
    assert "mark_resolved" in signals


def test_no_injection_signals_in_policy_docs():
    from pathlib import Path

    docs = Path(__file__).resolve().parent.parent / "docs"
    for name in ("alert_triage_guide.md", "high_value_transaction_review.md", "card_dispute_policy.md"):
        assert find_injection_signals((docs / name).read_text(encoding="utf-8")) == []
