"""
core/intent_classifier.py (SHIM)
================================
Shim for backward compatibility.
Logic moved to: intent/classifier.py
"""
from intent.classifier import classify_intent, Intent, is_llm_generatable

__all__ = ["classify_intent", "Intent", "is_llm_generatable"]
