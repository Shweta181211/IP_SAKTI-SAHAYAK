"""Conversational openers that must be answered before retrieval is attempted.

A vector store always returns its nearest passage, even when nothing is
relevant. So "hello" was being treated as a research question and answered with
"that is too short for me to search on" - technically correct, and a poor first
impression for the first thing many people type.

This idea is taken from the teammate's version (`rag_engine._conversation_response`),
which handled it better than ours did. Kept deliberately narrow: these patterns
must match the WHOLE message, so any real question - even a short one - falls
through to the normal retrieval path untouched.

Deterministic and free: no API call, so an outage cannot break a greeting.
"""

from __future__ import annotations

import re

GREETING = re.compile(
    r"^\s*(?:hello|hi|hey|hii+|yo|hola|namaste|namaskar|greetings|"
    r"good\s+(?:morning|afternoon|evening)|"
    r"हेलो|हाय|नमस्ते|नमस्कार)"
    r"[\s!.,?]*$",
    re.IGNORECASE,
)

CAPABILITY = re.compile(
    r"^\s*(?:(?:so\s+)?what\s+(?:can|do)\s+you\s+do|how\s+can\s+you\s+help|"
    r"who\s+are\s+you|what\s+is\s+this|help|what\s+are\s+you|"
    r"तुम\s*क्या\s*कर\s*सकते\s*हो|आप\s*क्या\s*कर\s*सकते\s*हैं|"
    r"यह\s*क्या\s*है)"
    r"[\s!.,?]*$",
    re.IGNORECASE,
)

THANKS = re.compile(
    r"^\s*(?:thanks|thank\s+you|thx|ty|great|got\s+it|ok(?:ay)?|"
    r"धन्यवाद|शुक्रिया)"
    r"[\s!.,?]*$",
    re.IGNORECASE,
)

_GREETING_REPLY = (
    "Hello. I answer questions about Indian law for Ayurvedic products - patents, "
    "trade marks, GI, copyright, biodiversity and ABS, drug and food regulation, and "
    "pharmacopoeial standards. Every answer cites the provision it relies on. "
    "What would you like to know?"
)

_CAPABILITY_REPLY = (
    "I look up Indian legal provisions for Ayurvedic products and explain them with "
    "citations you can check. I can tell you which regulatory category a product falls "
    "into, whether it can be patented, how to register a GI or trade mark, when you need "
    "National Biodiversity Authority approval, and what the labelling and advertising "
    "rules require. I only answer from a fixed corpus of Indian statutes and rules, so if "
    "something is outside that I will say so rather than guess."
)

_THANKS_REPLY = "You're welcome. Ask another question whenever you need to."

EXAMPLE_QUESTIONS = (
    "Can a classical churna from a First Schedule text be patented?",
    "How do I register a Geographical Indication for an Ayurvedic product?",
    "What is Access and Benefit Sharing and when do I need NBA approval?",
)


def conversational_reply(question: str) -> str | None:
    """Return a reply for small talk, or None to continue to retrieval."""
    if GREETING.match(question):
        return _GREETING_REPLY
    if CAPABILITY.match(question):
        return _CAPABILITY_REPLY
    if THANKS.match(question):
        return _THANKS_REPLY
    return None
