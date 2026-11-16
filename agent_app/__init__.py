"""Fraud Alert Agent — an LLM agent that investigates fraud alerts with
real tools, guardrails, human-in-the-loop approval, and full traces.

The LLM is a local Ollama model (free, no API keys). Tests inject a
scripted fake LLM, so the suite runs without Ollama.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
