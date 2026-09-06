"""Citation normalisation and validation - the anti-hallucination gate.

Two responsibilities:

1. **Build a citation you can put in front of a judge.** The corpus metadata
   field `section_or_clause` is unreliable: roughly 40% of its values are
   captured footnote text ("2. Ins. by Act 21 of 1962, s.2 (w.e.f. 27-7-1964)")
   rather than a provision heading. So we ignore it entirely and derive the
   reference from the chunk's own text, keeping only what we can confirm.

2. **Refuse anything unverifiable.** `validate_ids` is the choke point every
   model-produced citation passes through. An id that was not retrieved, or does
   not exist in the corpus, is dropped - never softened into a warning.

Design rule learned the hard way: a chunk's *own* numbered heading identifies it,
while an inline reference usually points elsewhere. Reading them in the wrong
order labels the D&C Act definitions clause as "Section 33C", because that clause
happens to mention a board constituted under section 33C.
"""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from typing import Any, Iterable

from .corpus_index import all_chunks, get_chunk
from .schemas import Citation

# Amendment/footnote chatter. Indian bare acts carry footnote blocks that look
# exactly like numbered headings, so this is what keeps them out.
FOOTNOTE_CUE = re.compile(
    r"Ins\.\s|Subs\.\s|Cl\.\s|w\.e\.f\.|ibid|G\.S\.R|S\.O\.\s|"
    r"omitted by|inserted by|substituted by|added by|re-?lettered|"
    r"earlier it was|vide notification|certain words",
    re.IGNORECASE,
)

# The numbered heading that opens a provision: "122E. Definition of new drug.-"
# or "3. Definitions.". Anchored near the start; that is what makes it the
# chunk's own provision rather than a cross-reference.
HEADING = re.compile(r"(\d{1,3}[A-Z]{0,2}(?:-[A-Z0-9]{1,3})?)\.\s*([A-Z][^.;]{2,90}?)\s*[.—–-]")

# A self-labelling reference, e.g. the marginal "Section 3(p)" the Manual of
# Patent Office Practice prints beside each provision it discusses.
EXPLICIT = re.compile(
    r"\b(Sections?|Rules?|Regulations?|Articles?)\s+"
    r"(\d{1,3}[A-Za-z]{0,2}(?:-[A-Za-z0-9]{1,3})?(?:\([a-zA-Z0-9]{1,4}\))*)"
)

# Phrases that mark a reference as pointing somewhere else in the statute book.
CROSSREF_CUE = re.compile(
    r"(?:under|below|above|in|of|to|by|see|per|referred to in|defined in|"
    r"specified in|constituted under|appointed under)\s+$",
    re.IGNORECASE,
)


def _normalise_ws(text: str) -> str:
    return " ".join(str(text).split())


def _noun_for(act_name: str) -> str:
    """Subordinate legislation has rules and regulations, not sections."""
    lowered = (act_name or "").lower()
    if "rules" in lowered:
        return "Rule"
    if "regulation" in lowered:
        return "Regulation"
    return "Section"


def _looks_like_footnote(fragment: str) -> bool:
    return bool(FOOTNOTE_CUE.search(fragment))


def _heading_number(text: str) -> str | None:
    """The raw leading heading number, with no reliability filtering."""
    for match in HEADING.finditer(text[:400]):
        title = match.group(2).strip()
        window = text[match.start() : match.start() + 160]
        if _looks_like_footnote(title) or _looks_like_footnote(window):
            continue
        if title.isupper() and len(title) > 12:
            continue
        return match.group(1)
    return None


@lru_cache(maxsize=64)
def _unreliable_numbers(doc_id: str) -> frozenset[str]:
    """Heading numbers that repeat within a document, and so cannot be sections.

    Schedules, forms and monographs restart their numbering on every page - the
    D&C Rules are full of "4. Standards", "5. Labelling" paragraphs that look
    exactly like provision headings. Real section numbers are essentially unique
    within an act, so a number appearing repeatedly is numbering of some other
    kind and must not be cited as a section.

    This is deliberately structural rather than a list of keywords: it adapts to
    whatever documents the corpus happens to contain.
    """
    counts: Counter[str] = Counter()
    for chunk in all_chunks():
        if chunk.get("doc_id") != doc_id:
            continue
        number = _heading_number(_normalise_ws(chunk["chunk_text"]))
        if number:
            counts[number] += 1
    return frozenset(number for number, count in counts.items() if count > 3)


def extract_section(chunk_text: str, act_name: str = "", doc_id: str = "") -> str | None:
    """Best verifiable reference to the provision this chunk *is*, or None.

    Returning None is a perfectly good outcome. Act plus page is honest; an
    invented or borrowed section number is not.
    """
    text = _normalise_ws(chunk_text)
    noun = _noun_for(act_name)

    # 1. The chunk's own opening heading, unless that number is schedule/form
    #    numbering rather than a provision number.
    number = _heading_number(text)
    if number and number not in _unreliable_numbers(doc_id):
        return f"{noun} {number}"

    # 2. Otherwise, self-labelling references - excluding pointers elsewhere.
    found: list[str] = []
    for match in EXPLICIT.finditer(text):
        before = text[max(0, match.start() - 40) : match.start()]
        if CROSSREF_CUE.search(before) or _looks_like_footnote(before):
            continue
        label = match.group(2).strip()
        if label not in found:
            found.append(label)

    if not found:
        return None
    # A chunk can legitimately span two provisions; naming both is more accurate
    # than silently picking the first.
    head = found[:2]
    return f"{noun}{'s' if len(head) > 1 else ''} " + ", ".join(head)


def build_citation(chunk_id: str, excerpt_chars: int = 600) -> Citation | None:
    """Turn a chunk id into a display-ready, verified citation."""
    chunk = get_chunk(chunk_id)
    if chunk is None:
        return None

    text = _normalise_ws(chunk["chunk_text"])
    act_name = str(chunk.get("act_name") or "Unknown source")
    section = extract_section(text, act_name, str(chunk.get("doc_id") or ""))

    # Belt and braces: never emit a number that is not literally in the text.
    if section:
        bare = re.sub(r"^(?:Sections?|Rules?|Regulations?|Articles?)\s+", "", section)
        if not all(part.strip() in text for part in bare.split(",")):
            section = None

    page = chunk.get("page_number")
    return Citation(
        chunk_id=chunk_id,
        act_name=act_name,
        section=section,
        page=int(page) if str(page).isdigit() else None,
        source_file=chunk.get("file_name"),
        regime=chunk.get("regime_type"),
        excerpt=text[:excerpt_chars],
    )


def validate_ids(
    candidate_ids: Iterable[Any], allowed_ids: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Split model-supplied citation ids into (kept, rejected).

    An id is kept only if it is BOTH a real corpus chunk AND was among the
    evidence actually retrieved for this question. The second condition matters:
    a model that recalls a real chunk id it was never shown is still guessing.
    """
    allowed = set(allowed_ids)
    kept: list[str] = []
    rejected: list[str] = []
    for raw in candidate_ids or []:
        cid = str(raw).strip()
        if cid and cid in allowed and get_chunk(cid) is not None:
            if cid not in kept:
                kept.append(cid)
        elif cid:
            rejected.append(cid)
    return kept, rejected


# Any doc/chunk-id-shaped token, however many digits, optionally bracketed.
#
# This was `DOC\d{3}_chunk_\d{3}` and lived only in comparison.py. Both facts
# were wrong. The fixed digit counts silently half-matched anything outside that
# shape - leaving "DOC3_chunk_45" or a four-digit index partly in the prose -
# and generation.py had no stripping at all, so the same model habit reached
# users through the reasoning steps.
_CHUNK_ID_IN_PROSE = re.compile(r"[\[\(]?DOC\d+_chunk_\d+[\]\)]?", re.IGNORECASE)


# Models narrate their own citing. Asked to put ids in `citation_ids` and not in
# prose, they instead write a placeholder where a footnote marker would go:
#
#   "...taxonomical identity, morphological description, habitat and collection
#    details the cited source."
#   "...excipient rules under Rules 168-169 the cited source, the cited source."
#
# Measured in TEST_RESULTS.md on BOTH models, up to seven times in one step, so
# it is a habit of the form rather than of one vendor. It changes no citation
# and no claim; it just makes finished legal prose look broken, and the citation
# cards beside it already say exactly what the source is.
#
# The leading punctuation is consumed with the phrase so that a repeat - ", the
# cited source, the cited source." - collapses cleanly instead of leaving a
# trail of commas.
_SOURCE_PLACEHOLDER = re.compile(
    r"[\s]*[,;(\[]?\s*\b(?:as\s+)?(?:per\s+|in\s+|from\s+)?"
    r"the\s+cited\s+sources?\b\s*[)\]]?",
    re.IGNORECASE,
)

# Left behind once the phrase goes: " ." or " ,", and doubled spaces.
_ORPHAN_PUNCT = re.compile(r"\s+([.,;:!?])")
_DOUBLE_SPACE = re.compile(r"[ \t]{2,}")


def strip_source_placeholders(text: str) -> str:
    """Remove "the cited source" narration the model splices into prose."""
    if not text:
        return text
    cleaned = _SOURCE_PLACEHOLDER.sub("", text)
    cleaned = _ORPHAN_PUNCT.sub(r"\1", cleaned)
    cleaned = _DOUBLE_SPACE.sub(" ", cleaned)
    return cleaned.strip()


def strip_chunk_ids(text: str) -> str:
    """Remove chunk ids the model wrote into prose.

    Models mention ids despite being told not to. The citation cards already
    carry them, and "DOC003_chunk_234 shows..." is noise to a reader who cannot
    look an id up. Stripping is display-only: `citation_ids` are untouched, so
    nothing about traceability changes.

    Two bugs lived in the two lines this replaced:

    1. The id was substituted with the literal phrase **"the cited source"**.
       No model ever wrote that phrase - we inserted it, in exactly the
       mid-sentence position the id had occupied, which is why it read as
       spliced in ("...habitat and collection details the cited source.") and
       why TEST_RESULTS.md saw it on both models and called it model chatter.
       A reader gains nothing from it: the source cards beside the answer
       already name the source. The id now goes, with any brackets around it.

    2. The tidy-up replacement was a literal SOH control character (0x01)
       instead of the backreference it was meant to be, so wherever a removal
       left " ." the sentence lost its full stop and gained an invisible
       control byte. It was committed that way, and it is invisible in every
       rendering of the file - it shows up only when you read the bytes.
    """
    original = text or ""
    cleaned = _CHUNK_ID_IN_PROSE.sub("", original)
    # An id at the very start takes the sentence's capital with it.
    led_with_id = bool(_CHUNK_ID_IN_PROSE.match(original.lstrip()))
    # Belt and braces: a model may still narrate a citation in words, and the
    # phrase is unwanted whoever produced it.
    cleaned = strip_source_placeholders(cleaned)
    # Close the gap a removal leaves before punctuation, KEEPING the punctuation.
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)|\[\s*\]", "", cleaned)   # brackets emptied by a removal
    # A removal can strand punctuation against punctuation (",.") or leave the
    # sentence opening on a comma. Both read as a bug.
    cleaned = re.sub(r"[,;:]+\s*([.!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:])\s*[,;:]+", r"\1", cleaned)
    cleaned = cleaned.lstrip(" ,;:")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if led_with_id and cleaned[:1].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


# A provision reference as it appears in prose: "Section 3(p)", "Rule 122-E",
# "section 11(2)(a)", "Regulation 7". The number is captured on its own so it
# can be looked for in the cited chunk's own text.
_PROVISION_IN_PROSE = re.compile(
    r"\b(?:section|sections|rule|rules|regulation|regulations)\s+"
    r"(\d+[A-Za-z]*(?:\s*[\u2010-\u2015-]\s*[A-Za-z0-9]+)?(?:\s*\([^)]{1,8}\))*)",
    re.IGNORECASE,
)

# Sentence boundary, kept deliberately simple. Legal prose here is model-written
# plain English, not statute, so "s.3(a)" style abbreviations do not appear.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


# "the Biological Diversity Rules 2024" and "the Trade Marks Act 1999" put a
# YEAR where the pattern above expects a provision number, and the year is part
# of the title, not a reference to Rule 2024. Left unguarded this deleted a
# perfectly good sentence about the 2024 Rules on the grounds that no chunk
# contains "Rule 2024" - which is true, and irrelevant.
#
# A bare four-digit number in the modern era is never a provision in this
# corpus; provisions are "3(p)", "122-E", "71", "11(2)(a)". Anything carrying a
# letter, bracket or hyphen is a real reference and is still checked.
def _is_year(token: str) -> bool:
    return token.isdigit() and len(token) == 4 and 1800 <= int(token) <= 2099


def _normalise_provision(token: str) -> str:
    """'122 - E', '122-E' and '122\u2013E' are the same provision."""
    return re.sub(r"[\s\u2010-\u2015-]", "", token).lower()


def provision_support(text: str, chunk_ids: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split provisions named in `text` into (supported, unsupported).

    Supported means the provision number occurs in the text of at least one of
    `chunk_ids`. This is the check that `validate_ids` does not do: that
    function proves a citation ID is real and was retrieved, which says nothing
    about whether the sentence beside it names a provision we actually hold.

    Measured on the flagship benchmark: in 2 of 6 cold runs the model wrote
    "Section 3(e)" into the legal-position step, and Section 3(e) appeared in
    NONE of the retrieved evidence - checked separately, 0 of 4 retrievals
    contained it. The citations shown next to that sentence were all valid, so
    the fabricated provision looked sourced. That is the "no fabricated
    authority" rule in CLAUDE.md 1.2, and nothing was enforcing it.
    """
    haystack = _normalise_provision(
        " ".join((get_chunk(cid) or {}).get("chunk_text", "") for cid in chunk_ids)
    )
    supported: list[str] = []
    unsupported: list[str] = []
    for match in _PROVISION_IN_PROSE.finditer(text or ""):
        token = match.group(1).strip()
        if _is_year(token):
            continue  # part of an Act's title, not a provision reference
        (supported if _normalise_provision(token) in haystack
         else unsupported).append(match.group(0))
    return supported, unsupported


def strip_unsupported_provisions(
    text: str, chunk_ids: Iterable[str]
) -> tuple[str, list[str]]:
    """Remove sentences that name a provision none of `chunk_ids` contains.

    The whole sentence goes, not just the reference. Deleting "Section 3(e)"
    from "Under Section 3(e), a mere admixture is not patentable" leaves a
    grammatical wreck that still asserts the claim; the sentence is the smallest
    unit that can be removed without misleading the reader.

    Callers pass the FULL evidence set, not the ids cited on that step. A
    provision that was retrieved but attributed to the wrong chunk is sloppy
    citing; one that appears nowhere in the evidence is invention. Only the
    second is worth mangling prose over.
    """
    if not text:
        return text, []
    kept: list[str] = []
    removed: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        _supported, unsupported = provision_support(sentence, chunk_ids)
        if unsupported:
            removed.extend(unsupported)
        else:
            kept.append(sentence)
    return " ".join(kept).strip(), removed


def citations_for(chunk_ids: Iterable[str]) -> list[Citation]:
    """Build citations for ids already validated. Unresolvable ids are skipped."""
    return [c for c in (build_citation(cid) for cid in chunk_ids) if c is not None]
