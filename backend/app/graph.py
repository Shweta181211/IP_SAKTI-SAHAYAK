"""A provision graph over the corpus — the relations text search cannot see.

Retrieval finds passages that *look like* the question. It cannot follow the one
structure legal text relies on most: statutes point at each other constantly.
A rule reads "a licence under rule 21", "in the manner specified in rule 69",
"subject to the conditions in rule 65" — and every one of those is a dead end
for a search engine, because the referenced provision shares almost no wording
with the question that retrieved the referring one.

This module builds the missing edge. It is deliberately **derived, never
authored**:

* Nodes are provisions the corpus already proves exist — taken from
  `citations._provision_spine`, the same structure that decides what a citation
  card displays. No provision is named here that the extractor could not place.
* Edges are cross-references found in the chunks' own text. Nothing is asserted
  about what a provision *means* or what it requires; the only claim made is
  "this passage mentions that provision", which is checkable by reading it.
* **No model is involved.** The graph cannot hallucinate a relation, and it
  costs no API quota to build or to use.

That last property is why this is worth having in a tool whose whole premise is
that claims must be traceable: a graph built by asking an LLM "what relates to
what" would be exactly the fabricated authority the rest of the pipeline exists
to prevent.

### What is deliberately NOT attempted

**Cross-document references.** Subordinate legislation constantly cites its
parent — the D&C Rules say "under section 18 of the Act" — and resolving "the
Act" to a specific document requires a hand-written map of which rules belong to
which statute. That is authored legal knowledge, so it is out. Instead a
reference resolves only when its noun matches the document's own
(`rule` inside Rules, `section` inside an Act, `regulation` inside Regulations),
which is precisely the test that keeps "section 18" in the Rules from being
mistaken for rule 18. Same-document references are the large majority and are
unambiguous; cross-document ones are simply left unlinked.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from .citations import (
    _is_year,
    _noun_for,
    _normalise_provision,
    _provision_spine,
)
from .corpus_index import all_chunks, get_chunk
from .schemas import Citation, RelatedProvision

logger = logging.getLogger(__name__)

# A reference as it appears in statutory prose: "under rule 21", "in section
# 6(1)", "specified in regulation 5". The noun is captured so it can be matched
# against the document's own — see the module docstring on why that matters.
#
# Written with an explicit character class rather than \b for the same reason
# the rest of this project does: an escape written through a patching script has
# turned into a literal backspace three times, and `tests/test_units.py` sweeps
# for it.
_REFERENCE = re.compile(
    r"(?<![A-Za-z])(section|rule|regulation|article)s?\s+"
    r"(\d{1,3}[A-Za-z]{0,2}(?:\s*[‐-―-]\s*[A-Za-z0-9]{1,3})?"
    r"(?:\s*\([^)]{1,8}\))*)(?!\d)",
    re.IGNORECASE,
)

# A provision list: "sections 3 and 6", "rules 122-D, 122-E and 122-F". Only a
# PLURAL noun licenses one, because "section 3 and 6 of the Schedule" is one
# reference followed by prose, not two provisions. Same number grammar as
# above, deliberately - a list item is a reference in every respect except that
# its noun was printed once for the whole list.
_LIST_CONTINUATION = re.compile(
    r"(?:\s*,\s*(?:and\s+)?|\s+and\s+)"
    r"(\d{1,3}[A-Za-z]{0,2}(?:\s*[‐-―-]\s*[A-Za-z0-9]{1,3})?"
    r"(?:\s*\([^)]{1,8}\))*)(?!\d)",
    re.IGNORECASE,
)

# How many graph-linked passages retrieval may add on top of its own top_k.
# Small on purpose: this is a supplement to search, not a replacement for it,
# and every added passage costs prompt room that fused retrieval had earned.
EXPANSION_SLOTS = 3

# A provision cited by half the document is boilerplate ("in accordance with
# rule 3"), not a meaningful relation. Edges above this are dropped as noise.
MAX_INBOUND_FOR_SIGNAL = 40

# Which documents have a provision structure worth linking at all.
#
# The graph reads "section 12" and resolves it against the document's own
# provision spine. That only means something where the numbered provisions ARE
# the document's structure - statutes and the rules made under them. Elsewhere
# the same numerals are something else entirely, and the spine happily places
# them:
#
#   pharmacopoeia_reference  the Ayurvedic Formulary's "SECTION 10 VATI AND
#                            GUTIKA" is a book division, and "10. Sadananda
#                            Sharma, Rasatarangini" is an entry in its
#                            bibliography. Linking one to the other is nonsense
#                            presented as a cross-reference.
#   registry_guideline       the Manual of Patent Office Practice numbers its
#                            own paragraphs; "Section 9" in its margin is a
#                            reference to the Patents Act, which is a DIFFERENT
#                            document, so resolving it locally is the
#                            cross-instrument error in another costume.
#   international_treaty     treaties number by Article, and `_noun_for` calls
#                            everything without "rules" in its name a Section,
#                            so a table of contents resolves against itself.
#
# Measured over the whole corpus: this keeps 602 of 641 edges and removes every
# family that a hand audit found wrong. The alternative - patching each case -
# would be a list of document names, which is the thing this project does not do.
LINKABLE_REGIMES = frozenset({"ip_statute", "drug_regulatory_classification"})


@dataclass(frozen=True)
class ProvisionNode:
    """One provision, as the corpus proves it exists."""

    doc_id: str
    act_name: str
    #: Bare number as the spine records it — "21", "122D", "3".
    number: str

    @property
    def label(self) -> str:
        return f"{_noun_for(self.act_name)} {self.number}"


@lru_cache(maxsize=1)
def _provision_index() -> dict[tuple[str, str], list[str]]:
    """(doc_id, normalised provision) -> the chunks that ARE that provision.

    The inverse of the provision spine. A provision usually spans several
    chunks, so this is a list and the first entry is the one that opened it.
    """
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for chunk in all_chunks():
        by_doc[str(chunk.get("doc_id") or "")].append(chunk)

    for doc_id, chunks in by_doc.items():
        if not doc_id:
            continue
        if str(chunks[0].get("regime_type") or "") not in LINKABLE_REGIMES:
            continue  # not a document whose numbers are provisions - see above
        spine = _provision_spine(doc_id)
        if not spine:
            continue
        chunks.sort(key=lambda c: int(str(c["chunk_id"]).rsplit("_", 1)[1]))
        for chunk in chunks:
            number = spine.get(str(chunk["chunk_id"]))
            if number:
                index[(doc_id, _normalise_provision(number))].append(
                    str(chunk["chunk_id"])
                )
    return dict(index)


# A reference that names another instrument belongs to that instrument, not to
# this one. Statutes do this constantly:
#
#     "...appointed under sub-section (1) of section 4 of the Trade and
#      Merchandise Marks Act, 1958"          <- the Designs Act citing another act
#     "...a public servant within the meaning of section 21 of the Indian Penal
#      Code"                                 <- the GI Act citing the IPC
#
# Both were resolved to the CITING act's own section 4 and section 21 before
# this guard existed, producing a confident link to an unrelated provision -
# exactly the mis-citation this project refuses to ship. Matching the noun to the
# document is not enough on its own, because both said "section" inside an Act.
#
# "of this Act" is the opposite case and stays: it is an explicit self-reference.
_OTHER_INSTRUMENT = re.compile(
    r"^\s*(?:,\s*)?(?:of|under|in)\s+(?:the|that|said)\s", re.IGNORECASE
)
_SELF_INSTRUMENT = re.compile(r"^\s*(?:,\s*)?(?:of|under|in)\s+this\s", re.IGNORECASE)


def _references_in(text: str, act_name: str) -> set[str]:
    """Provisions this text points at, within its OWN document.

    Two filters, and both are needed:

    * the reference's noun must match the document's own, so "section 18 of the
      Act" inside the D&C Rules is not read as rule 18;
    * the reference must not name another instrument - see `_OTHER_INSTRUMENT`.
    """
    own_noun = _noun_for(act_name).lower()
    found: set[str] = set()
    text = text or ""
    for match in _REFERENCE.finditer(text):
        noun = match.group(1).lower()
        if noun != own_noun:
            continue

        tokens = [match.group(2).strip()]
        end = match.end()
        # "sections 3 and 6" is two references sharing one noun. Gathered
        # BEFORE the instrument test below, because the phrase that names
        # another instrument sits after the LAST item - "sections 4 and 5 of
        # the Trade and Merchandise Marks Act" must lose both, not one.
        if text[match.end(1) : match.end(1) + 1].lower() == "s":
            while (cont := _LIST_CONTINUATION.match(text, end)) is not None:
                tokens.append(cont.group(1).strip())
                end = cont.end()

        trailing = text[end : end + 40]
        if _OTHER_INSTRUMENT.match(trailing) and not _SELF_INSTRUMENT.match(trailing):
            continue
        for token in tokens:
            if _is_year(token):
                continue  # "the Rules 2024" is a title, not a reference
            found.add(_normalise_provision(token))
    return found


@lru_cache(maxsize=1)
def _edges() -> dict[str, list[tuple[str, str]]]:
    """chunk_id -> [(referenced chunk_id, the provision label it points at)].

    Built once. Self-references are dropped: a chunk that IS rule 21 naturally
    says "rule 21", and linking a provision to itself is noise.
    """
    index = _provision_index()
    inbound: dict[str, int] = defaultdict(int)
    raw: dict[str, list[tuple[str, str]]] = {}

    for chunk in all_chunks():
        chunk_id = str(chunk["chunk_id"])
        doc_id = str(chunk.get("doc_id") or "")
        act_name = str(chunk.get("act_name") or "")
        if not doc_id or not act_name:
            continue
        if str(chunk.get("regime_type") or "") not in LINKABLE_REGIMES:
            continue
        text = " ".join(str(chunk["chunk_text"]).split())
        own = _provision_spine(doc_id).get(chunk_id)
        own_key = _normalise_provision(own) if own else None

        links: list[tuple[str, str]] = []
        for reference in _references_in(text, act_name):
            if own_key and reference == own_key:
                continue
            targets = index.get((doc_id, reference))
            if not targets:
                continue
            # The target must be a chunk that actually SHOWS the provision's
            # own heading. Preferring one and falling back to the first chunk
            # the spine placed was not enough: where the spine placed a chunk
            # by inheritance and nothing in the document ever prints that
            # heading, the fallback linked to a passage that is not the
            # provision at all - measured, it sent a reader from an Ayurvedic
            # Formulary page headed "SECTION 1 ASAVA AND ARISTA" to an index of
            # recipe names. A link we cannot point at is a link we do not make.
            target = None
            for candidate in targets:
                candidate_chunk = get_chunk(candidate)
                if candidate_chunk is None:
                    continue
                if _opening_at(
                    " ".join(str(candidate_chunk["chunk_text"]).split()), reference
                ) >= 0:
                    target = candidate
                    break
            if target is None or target == chunk_id:
                continue
            label = f"{_noun_for(act_name)} {reference}"
            links.append((target, label))
            inbound[target] += 1
        if links:
            raw[chunk_id] = links

    # Drop boilerplate targets: a provision referenced by most of the document
    # ("in accordance with rule 3") carries no information about any one passage.
    noisy = {cid for cid, n in inbound.items() if n > MAX_INBOUND_FOR_SIGNAL}
    if noisy:
        logger.info("Graph: dropping %d over-referenced provisions as boilerplate", len(noisy))
    pruned = {
        chunk_id: [(t, lbl) for t, lbl in links if t not in noisy]
        for chunk_id, links in raw.items()
    }
    return {cid: links for cid, links in pruned.items() if links}


def _opening_at(text: str, number: str) -> int:
    """Where the provision's own heading starts in this text, or -1.

    A chunk that opens a provision does not always open with it: the Indian
    Kanoon extractions carry the previous provision's amendment footnote first,
    so a link to Rule 157 could show a reader a fragment of Rule 153-A. Same
    lesson as the classification anchors in section 6o - the text was right and
    the window was wrong.
    """
    pattern = re.compile(
        r"(?<![0-9A-Za-z])" + re.escape(number.rstrip(".")) + r"[.\s]",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        # A heading is followed by a title or a dash, not by more digits.
        after = text[match.end() : match.end() + 40].lstrip(" .[-")
        if after[:1].isalpha():
            return match.start()
    return -1


def references_from(chunk_id: str) -> list[RelatedProvision]:
    """The provisions this passage points at, resolved to real chunks."""
    out: list[RelatedProvision] = []
    seen: set[str] = set()
    for target, label in _edges().get(chunk_id, []):
        if target in seen:
            continue
        seen.add(target)
        chunk = get_chunk(target)
        if chunk is None:
            continue
        text = " ".join(str(chunk["chunk_text"]).split())
        number = label.split()[-1]
        at = _opening_at(text, number)
        excerpt = (text[at : at + 400] if at > 0 else text[:400])
        out.append(
            RelatedProvision(
                chunk_id=target,
                act_name=str(chunk.get("act_name") or "Unknown source"),
                provision=label,
                page=int(chunk["page_number"]) if str(chunk.get("page_number")).isdigit() else None,
                excerpt=excerpt,
            )
        )
    return out


@lru_cache(maxsize=1)
def _inbound() -> dict[str, list[tuple[str, str]]]:
    """target chunk_id -> [(the chunk that points at it, the label it used)].

    The reverse direction is worth having on its own. Outbound answers "what
    does this provision defer to"; inbound answers "what relies on this one",
    which is how a reader judges whether a provision is load-bearing. It also
    roughly doubles the number of citations that can show anything at all -
    only 11% of chunks make an outbound reference.
    """
    back: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for source, links in _edges().items():
        for target, label in links:
            back[target].append((source, label))
    return dict(back)


def referenced_by(chunk_id: str, limit: int = 4) -> list[RelatedProvision]:
    """Provisions that point AT this one."""
    out: list[RelatedProvision] = []
    seen: set[str] = set()
    for source, _label in _inbound().get(chunk_id, []):
        if source in seen or len(out) >= limit:
            continue
        seen.add(source)
        chunk = get_chunk(source)
        if chunk is None:
            continue
        text = " ".join(str(chunk["chunk_text"]).split())
        # Label the SOURCE by what it is, not by the reference it made.
        own = _provision_spine(str(chunk.get("doc_id") or "")).get(source)
        if not own:
            # A source the spine cannot place has no provision to name, and
            # "referenced by The Drugs and Cosmetics Rules 1945" tells a reader
            # nothing they can go and read. Skip it rather than label it vaguely.
            continue
        act_name = str(chunk.get("act_name") or "Unknown source")
        label = f"{_noun_for(act_name)} {own}"
        at = _opening_at(text, own)
        out.append(
            RelatedProvision(
                chunk_id=source,
                act_name=act_name,
                provision=label,
                page=int(chunk["page_number"]) if str(chunk.get("page_number")).isdigit() else None,
                excerpt=(text[at : at + 400] if at > 0 else text[:400]),
                direction="inbound",
            )
        )
    return out


def attach_links(citations: list[Citation]) -> list[Citation]:
    """Give each citation the provisions its own text points at.

    Display only — it adds no claim to the answer. A reader looking at a rule
    that says "subject to rule 21" can read rule 21 instead of hitting the dead
    end the search engine left them at.
    """
    for citation in citations:
        outbound = references_from(citation.chunk_id)
        # Inbound only fills the gap left by outbound, so a citation that
        # already shows what it defers to is not padded with what defers to it.
        room = max(0, 4 - len(outbound))
        citation.related = outbound + (referenced_by(citation.chunk_id, room) if room else [])
    return citations


def expand(chunk_ids: list[str], limit: int = EXPANSION_SLOTS) -> list[str]:
    """Provisions the retrieved passages point at, that retrieval did not find.

    Ordered by how many of the retrieved passages point at them, so a provision
    two different rules defer to outranks one mentioned in passing. Bounded, and
    never returns anything already retrieved.
    """
    if not chunk_ids or limit <= 0:
        return []
    have = set(chunk_ids)
    votes: dict[str, int] = defaultdict(int)
    for chunk_id in chunk_ids:
        for target, _label in _edges().get(chunk_id, []):
            if target not in have:
                votes[target] += 1
    ranked = sorted(votes.items(), key=lambda pair: (-pair[1], pair[0]))
    return [cid for cid, _ in ranked[:limit]]


@lru_cache(maxsize=1)
def stats() -> dict[str, int]:
    """Shape of the graph, for /health and for saying something true about it."""
    edges = _edges()
    index = _provision_index()
    targets = {t for links in edges.values() for t, _ in links}
    return {
        "provisions": len(index),
        "passages_with_references": len(edges),
        "references": sum(len(v) for v in edges.values()),
        "provisions_referenced": len(targets),
    }


def verify() -> list[str]:
    """Startup check: a graph pointing at chunks that no longer exist is worse
    than no graph, because every link it offers would 404 a reader."""
    problems: list[str] = []
    edges = _edges()
    if not edges:
        problems.append("provision graph is empty - no cross-references resolved")
        return problems
    dangling = 0
    for links in edges.values():
        for target, _label in links:
            if get_chunk(target) is None:
                dangling += 1
    if dangling:
        problems.append(f"provision graph has {dangling} links to missing chunks")
    return problems
