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
# or "3. Definitions.".
#
# The optional bracket before the title is not cosmetic. Several documents in
# this corpus are Indian Kanoon scrapes, whose convention is to wrap any
# provision that has ever been amended in square brackets and inline the
# amendment note straight after it:
#
#     31. [ Standard for certain imported drugs. [Substituted by G.S.R. 604(E)...
#
# Without allowing that bracket the title match fails on "[" and the whole
# heading is lost. In the Drugs and Cosmetics Rules 1945 - the most heavily
# amended document here - that one character accounted for the majority of
# unidentified provisions.
#
# "]" is accepted as a title terminator for the same reason: a heading can end
# on an amended phrase rather than a full stop, as in
# "52. Duties of Inspectors ... the manufacture of [drugs or cosmetics]".
HEADING = re.compile(
    r"(\d{1,3}[A-Z]{0,2}(?:-[A-Z0-9]{1,3})?)\.\s*(\[\s*)?([A-Z][^.;]{2,90}?)\s*[.\]—–-]"
)

# A provision whose heading text was itself substituted away, leaving the
# number, a bracket and the amendment note:
#
#     41. [ [Substituted by S.O. 218, dated 15.1.1954.] (1)If the Director...
#
# The number is still the rule number, and "Rule 41" is still the right
# citation. Distinguished from a footnote block by the bracket: a footnote
# block opens with its cue ("2. Ins. by Act 21 of 1962"), never with "[".
HEADING_AMENDED_AWAY = re.compile(r"(\d{1,3}[A-Z]{0,2}(?:-[A-Z0-9]{1,3})?)\.\s*\[\s*\[")

# A chunk that opens on a chapter, part or schedule heading begins a new
# structural division of the document, so whatever provision ran above it has
# ended and must not be inherited across the boundary.
STRUCTURAL_DIVIDER = re.compile(
    r"^(?:THE\s+)?(?:CHAPTER|PART|SCHEDULE|ANNEX(?:URE)?|APPENDIX)\b", re.IGNORECASE
)

# How far into the text after a heading number a footnote cue may start before
# the "heading" is judged to be a footnote block rather than a provision.
#
# This replaces a flat 160-character forward window, which could not tell these
# two apart:
#
#     2. Ins. by Act 21 of 1962, s.2 (w.e.f. 27-7-1964).   <- footnote block
#     31. [ Standard for certain imported drugs. [Substituted by ...  <- heading
#
# Both carry a cue within 160 characters, so the old check rejected both. The
# discriminator is WHERE the cue sits: a footnote block *opens* with its cue,
# while a real heading puts its title first and the amendment note after it.
FOOTNOTE_LEAD_CHARS = 6

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


# An enumerated list is not a provision. Schedule H drug lists, First Schedule
# book lists, equipment schedules and blocks of amendment footnotes all pack
# many numbered entries into one chunk, and any one of those numbers can be
# mistaken for the heading of the provision the chunk belongs to. Measured on
# this corpus, that produced "Rule 170" for a list of drug names, "Section 1"
# for the First Schedule list of Ayurvedic texts, and a section number for 60+
# blocks of pure footnote text.
#
# A real provision opens with one heading; the corpus distribution is stark -
# provisions carry 1 numbered entry, lists carry 5 to 15. So a chunk with this
# many distinct numbered entries is a list, and gets act plus page.
LIST_ENTRY = re.compile(
    r"(?:^|\s)(\d{1,3}[A-Z]{0,2}(?:-[A-Z0-9]{1,3})?)\.\s+(?=[A-Za-z\[])"
)
MAX_NUMBERED_ENTRIES = 4


def _is_enumerated_list(text: str) -> bool:
    """Is this chunk a numbered list rather than a provision?"""
    return len(set(LIST_ENTRY.findall(text[:400]))) > MAX_NUMBERED_ENTRIES


def _opens_with_footnote_cue(after_number: str) -> bool:
    """Does a footnote cue START this fragment, rather than merely appear in it?

    See FOOTNOTE_LEAD_CHARS. A footnote block leads with its cue; a provision
    heading leads with its title and carries the amendment note afterwards.
    """
    match = FOOTNOTE_CUE.search(after_number[:160])
    return bool(match) and match.start() <= FOOTNOTE_LEAD_CHARS


def _heading_number(text: str) -> str | None:
    """The raw leading heading number, with no reliability filtering."""
    if _is_enumerated_list(text):
        return None
    window = text[:400]
    for match in HEADING.finditer(window):
        title = match.group(3).strip()
        bracketed = match.group(2) is not None
        after_number = window[match.end(1) + 1 :]
        # A bracketed title is an amended provision, so the amendment note that
        # follows it is expected and says nothing about whether this is a
        # heading. An unbracketed one is only a heading if it does not open on
        # a footnote cue.
        if not bracketed and _opens_with_footnote_cue(after_number):
            continue
        if _looks_like_footnote(title):
            continue
        if title.isupper() and len(title) > 12:
            continue
        return match.group(1)

    # No titled heading. The provision may still be identifiable if its heading
    # text was amended away entirely, which leaves the number intact.
    amended = HEADING_AMENDED_AWAY.search(window)
    if amended:
        return amended.group(1)
    return None


# Two different bounds, for two different risks.
#
# LINK is how far apart two headings may sit and still be read as consecutive
# provisions of one ascending sequence. It exists to stop the chain walking out
# of the provision body and into a schedule: measured on the D&C Rules, the body
# ends at Rule 166 around chunk 254 and Schedule H's drug list ("391.
# D-PENICILLAMINE", "440. ROPINIROLE") resumes ascending numbering 289 chunks
# later. Unbounded, the chain hops that gap and cites drug names as Rules 230,
# 285, 342, 393 and 444.
#
# CARRY is how many consecutive chunks may inherit a provision number from the
# heading above them. It is much tighter because its failure mode is worse: a
# link that is wrong costs one citation, while an over-long carry mislabels
# every chunk it covers. A rule spans a handful of chunks, never dozens.
SPINE_MAX_LINK_GAP = 40
SPINE_MAX_CARRY = 6


@lru_cache(maxsize=64)
def _repeated_numbers(doc_id: str) -> frozenset[str]:
    """Heading numbers that repeat within a document, and so cannot be unique.

    Schedules, forms and monographs restart their numbering on every page - the
    D&C Rules are full of "4. Standards", "5. Labelling" paragraphs that look
    exactly like provision headings. A real provision number is essentially
    unique within an act, so a number appearing repeatedly is numbering of some
    other kind and must not be cited on the strength of the heading alone.

    This is the project's original filter and it is kept unchanged, because for
    a chunk the provision spine cannot place it is still the best test there is.
    What changed is that it is no longer the ONLY test: it used to ban a number
    across the whole document, so the D&C Rules lost real Rules 2, 3 and 5 to
    the schedule paragraphs that reuse those numbers later. The spine now
    rescues exactly those, by placing them in the document's own ascending
    sequence; this filter still governs everything the spine has no view on.
    """
    counts: Counter[str] = Counter()
    for chunk in all_chunks():
        if chunk.get("doc_id") != doc_id:
            continue
        number = _heading_number(_normalise_ws(chunk["chunk_text"]))
        if number:
            counts[number] += 1
    return frozenset(number for number, count in counts.items() if count > 3)


def _chunk_ordinal(chunk: dict) -> int:
    """Position of a chunk within its document, from the trailing index."""
    try:
        return int(str(chunk["chunk_id"]).rsplit("_", 1)[1])
    except (KeyError, IndexError, ValueError):
        return 0


def _provision_key(number: str) -> tuple[int, str] | None:
    """Sortable form of a provision number: '122-E' -> (122, 'E'), '3' -> (3, '')."""
    match = re.match(r"(\d{1,3})[-]?([A-Za-z0-9]{0,3})$", number or "")
    if not match:
        return None
    return int(match.group(1)), match.group(2).upper()


@lru_cache(maxsize=64)
def _provision_spine(doc_id: str) -> dict[str, str]:
    """Map every identifiable chunk of a document to the provision it belongs to.

    This replaces a frequency filter that suppressed any heading number
    appearing more than three times in a document. The intent was right -
    schedules, forms and monographs restart their numbering on every page, so
    "5. Capsules" in Schedule M is not Rule 5 - but the instrument was blunt:
    in the D&C Rules 1945 it banned the numbers 1-14 and 23 outright, which
    threw away **316 correctly detected real rules** along with the schedule
    paragraphs. That single filter, not the heading regex, was the main reason
    this document cited a provision for only 11% of its chunks.

    The structural fact it missed is that a statute's provision numbers ASCEND
    through the document, while schedule numbering restarts. So instead of
    asking "is this number repeated?", build the longest chain of detected
    headings that is non-decreasing in provision number and locally contiguous
    in the document. That chain is the provision body; headings that cannot
    join it are the restarts, and are refused exactly as before.

    Two properties fall out of this that the frequency filter could not give:

    * Rules 2, 3 and 5 are citable again, because in the body they appear once,
      in order - it is only the schedules that repeat those numbers later.
    * Chunks BETWEEN two consecutive chain members are continuations of the
      earlier one, so they inherit its number. That is what puts a rule number
      on the 404 chunks that carry no heading of their own because the
      provision began on the previous chunk. The inheritance is bounded by
      SPINE_MAX_GAP by construction, so it can never run across a document.

    Still structural, still no per-document special-casing, and still biased
    towards under-citing: a chunk the chain cannot place gets act plus page.
    """
    chunks = [c for c in all_chunks() if c.get("doc_id") == doc_id]
    if not chunks:
        return {}
    chunks.sort(key=_chunk_ordinal)

    # (position in document, chunk_id, heading number, sortable key)
    candidates: list[tuple[int, str, str, tuple[int, str]]] = []
    for position, chunk in enumerate(chunks):
        number = _heading_number(_normalise_ws(chunk["chunk_text"]))
        key = _provision_key(number) if number else None
        if number and key:
            candidates.append((position, str(chunk["chunk_id"]), number, key))
    if not candidates:
        return {}

    # Longest non-decreasing chain under a positional bound. Scanning backwards
    # and breaking on the bound is safe: any earlier candidate sits at an even
    # greater distance.
    length = [1] * len(candidates)
    previous = [-1] * len(candidates)
    for b in range(len(candidates)):
        for a in range(b - 1, -1, -1):
            if candidates[b][0] - candidates[a][0] > SPINE_MAX_LINK_GAP:
                break
            if candidates[a][3] <= candidates[b][3] and length[a] + 1 > length[b]:
                length[b] = length[a] + 1
                previous[b] = a

    end = max(range(len(candidates)), key=lambda i: length[i])
    chain: list[int] = []
    while end != -1:
        chain.append(end)
        end = previous[end]
    chain.reverse()

    spine: dict[str, str] = {}
    for rank, index in enumerate(chain):
        position, chunk_id, number, _key = candidates[index]
        spine[chunk_id] = number
        # Chunks between this heading and the next one on the chain continue
        # this provision, so they carry its number. Only BETWEEN members: after
        # the last one there is no bound on how far the document runs on, and
        # in the D&C Rules what follows the final rule is the schedules.
        if rank + 1 < len(chain):
            next_position = candidates[chain[rank + 1]][0]
            if next_position - position - 1 > SPINE_MAX_CARRY:
                continue
            heading_page = chunks[position].get("page_number")
            for between in range(position + 1, next_position):
                following = chunks[between]
                # Only into chunks with no heading of their own. A chunk that
                # does carry a heading is making its own claim about which
                # provision it is; overriding that with an inherited number
                # would be a downgrade, not a repair, so it is left to the
                # frequency filter to judge as before.
                if _heading_number(_normalise_ws(following["chunk_text"])):
                    continue
                # And only within the same printed page. Chunk adjacency alone
                # was not enough: it inherited "Section 1" onto an Ayurvedic
                # Formulary recipe and a section number onto a block of pure
                # amendment footnotes. A continuation that is still on the page
                # the heading was printed on is almost certainly the same
                # provision; once the page turns, that stops being true and the
                # honest citation is the act plus the page.
                if (
                    heading_page is None
                    or following.get("page_number") != heading_page
                ):
                    continue
                # A structural divider ends the provision above it. Without
                # this a lone "CHAPTER VI FARMERS' RIGHTS" chunk inherited the
                # section number of whatever preceded it on the page.
                if STRUCTURAL_DIVIDER.match(_normalise_ws(following["chunk_text"])):
                    continue
                spine[str(following["chunk_id"])] = number
    return spine


def extract_section(
    chunk_text: str,
    act_name: str = "",
    doc_id: str = "",
    chunk_id: str = "",
) -> str | None:
    """Best verifiable reference to the provision this chunk *is*, or None.

    Returning None is a perfectly good outcome. Act plus page is honest; an
    invented or borrowed section number is not.

    `chunk_id` is optional so existing callers keep working, but supplying it is
    what allows the document's provision spine to place a chunk that carries no
    heading of its own - the common case in the middle of a long rule.
    """
    text = _normalise_ws(chunk_text)
    noun = _noun_for(act_name)

    # 1. Where the document's own provision sequence places this chunk. See
    #    _provision_spine: this both accepts real numbers the old frequency
    #    filter suppressed and rejects schedule numbering it could not see.
    if chunk_id and doc_id:
        placed = _provision_spine(doc_id).get(chunk_id)
        if placed:
            return f"{noun} {placed}"

    # 2. Otherwise the original rule, unchanged: the chunk's own opening
    #    heading, unless that number repeats within the document and so is
    #    schedule or form numbering. Keeping this as a fallback rather than
    #    replacing it is what makes the spine strictly additive - every citation
    #    the previous implementation produced is still produced.
    number = _heading_number(text)
    if number and number not in _repeated_numbers(doc_id):
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
    section = extract_section(
        text, act_name, str(chunk.get("doc_id") or ""), chunk_id
    )

    # Belt and braces: never emit a number that is not literally in the text.
    #
    # This applies only to a reference read OUT of this chunk. A number the
    # provision spine inherited from the heading above is by definition not in
    # this chunk's own text - that is what makes it a continuation - so running
    # the check on it was incoherent in both directions: it voided correctly
    # inherited numbers, while passing "Rule 3" for any chunk that happened to
    # contain a "3" inside a date.
    inherited = bool(chunk_id) and chunk_id in _provision_spine(
        str(chunk.get("doc_id") or "")
    )
    if section and not inherited:
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


# "International Patent Office" is not an institution. Patents are granted by
# national offices (the Indian Patent Office, the USPTO) and regional ones (the
# EPO); WIPO administers treaties and does not grant patents.
#
# This needs a guard as well as a prompt rule because the phrase is IN THE
# CORPUS: About TKDL.pdf reads "prevent its misappropriation at International
# Patent Offices", meaning "patent offices internationally". A model answering
# strictly from that evidence reproduces it in its own prose, and measured over
# six probe questions it did so in two of them - including the flagship. The
# prompt asks; this makes sure.
#
# Display-only, and only over prose the MODEL wrote. Citation excerpts are
# verbatim corpus text and are never rewritten - if the source says it, the
# source card shows it saying it.
_FICTIONAL_OFFICE = re.compile(
    r"(?:the\s+)?\bInternational\s+Patent\s+Offices?\b", re.IGNORECASE
)


def normalise_institutions(text: str) -> str:
    """Replace institutions that do not exist with an accurate generic phrase."""
    if not text:
        return text
    return _FICTIONAL_OFFICE.sub("patent offices in other countries", text)

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


# A sub-clause reference, split into its provision and its clause markers:
# "11(1)" -> ("11", ["1"]);  "2(1)(e)" -> ("2", ["1", "e"]).
_SUBCLAUSE = re.compile(
    r"^([0-9]+[A-Za-z]*(?:[‐-―-][A-Za-z0-9]+)?)((?:\([^)]{1,8}\))+)$"
)


def _subclause_supported(token: str, chunk_ids: list[str]) -> bool:
    """Is "Section 11(1)" supported by a chunk that IS section 11 and shows (1)?

    The literal test above asks whether the string "11(1)" occurs in the
    evidence. Statutes almost never write that: the GI Act prints
    "11. Application for registration.-(1) Any association of persons...", so a
    perfectly correct reference to section 11(1) matched nothing and the whole
    sentence carrying it was deleted. Measured on a GI question: three correct
    references (2(1)(e), 11(1), 11(2)(a)) were all called invented, and the
    Legal position step - the one a reader actually needs - shipped empty.

    So a sub-clause reference is also supported when a retrieved chunk **is**
    that provision (per the provision spine) **and** carries that clause marker.
    That is deliberately much narrower than "the base number appears somewhere
    in the evidence", which would have re-opened the exact hole section 6k
    closed: a chunk merely MENTIONING section 3 would then support a fabricated
    "Section 3(e)". Here the chunk has to be section 3 itself.

    Verified against both cases: it restores all three GI references, and adds
    nothing at all to the flagship's evidence set, where no retrieved chunk is
    spine-placed as a base provision.
    """
    match = _SUBCLAUSE.match(re.sub(r"\s+", "", token))
    if not match:
        return False
    base = _normalise_provision(match.group(1))
    markers = re.findall(r"\(([^)]{1,8})\)", match.group(2))
    for chunk_id in chunk_ids:
        chunk = get_chunk(chunk_id)
        if not chunk:
            continue
        placed = _provision_spine(str(chunk.get("doc_id") or "")).get(chunk_id)
        if not placed or _normalise_provision(placed) != base:
            continue
        if all(f"({marker})" in chunk.get("chunk_text", "") for marker in markers):
            return True
    return False


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
    ids = list(chunk_ids)
    haystack = _normalise_provision(
        " ".join((get_chunk(cid) or {}).get("chunk_text", "") for cid in ids)
    )
    supported: list[str] = []
    unsupported: list[str] = []
    for match in _PROVISION_IN_PROSE.finditer(text or ""):
        token = match.group(1).strip()
        if _is_year(token):
            continue  # part of an Act's title, not a provision reference
        ok = _normalise_provision(token) in haystack or _subclause_supported(token, ids)
        (supported if ok else unsupported).append(match.group(0))
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
