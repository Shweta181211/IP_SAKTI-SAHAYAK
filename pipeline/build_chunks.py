#!/usr/bin/env python3
"""Extract and structure legal PDF text for an Ayurveda IP-law RAG corpus.

The script prefers pdfplumber, falls back to pypdf, and attempts OCR only when
ordinary extraction yields very little text. It is safe to rerun: generated
raw text, chunks, and logs are replaced on each execution.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pdfplumber
from pypdf import PdfReader


FOLDER_TO_REGIME = {
    "01_classification": "drug_regulatory_classification",
    "02_national_statutes": "ip_statute",
    "03_international": "international_treaty",
    "03_international(later)": "international_treaty",
    "04_registries": "registry_guideline",
    "05_pharmacopoeia": "pharmacopoeia_reference",
}

# A heading must occupy a line by itself. This keeps references such as
# "under Section 3" in running prose from becoming false chunk boundaries.
HEADER_RE = re.compile(
    r"^\s*(?:(?:CHAPTER|PART)\s+[IVXLCDM0-9]+(?:\s*[-:.].*)?|"
    r"(?:SECTION|SEC\.?|RULE|ARTICLE|CLAUSE)\s+\d+(?:\s*\([^)]+\))*"
    r"(?:\s*[-:.].*)?|\d+(?:\.\d+)*(?:\s*\([a-z0-9]+\))*\s*[-:.]\s*.+)\s*$",
    re.IGNORECASE,
)
SECTION_ID_RE = re.compile(
    r"\b(?:SECTION|SEC\.?|RULE|ARTICLE|CLAUSE)\s+\d+(?:\s*\([^)]+\))*|"
    r"\b(?:CHAPTER|PART)\s+[IVXLCDM0-9]+", re.IGNORECASE,
)
TOKEN_RE = re.compile(r"\S+")


@dataclass
class Piece:
    text: str
    pages: list[int]
    section: str


def token_count(text: str) -> int:
    """Approximate embedding-model tokens with whitespace-delimited words."""
    return len(TOKEN_RE.findall(text))


def clean_text(text: str | None) -> str:
    """Normalize extraction artifacts without altering paragraph structure."""
    if not text:
        return ""
    text = text.replace("\x00", "").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_with_pdfplumber(pdf: Path) -> list[str]:
    pages: list[str] = []
    with pdfplumber.open(pdf) as document:
        for page in document.pages:
            # layout=True better preserves legal headings and indented clauses.
            pages.append(clean_text(page.extract_text(layout=True) or page.extract_text()))
    return pages


def extract_with_pypdf(pdf: Path) -> list[str]:
    reader = PdfReader(str(pdf))
    return [clean_text(page.extract_text() or "") for page in reader.pages]


def ocr_pdf(pdf: Path, page_count: int) -> list[str]:
    """OCR one page at a time, keeping memory bounded for long government PDFs."""
    try:
        import pytesseract  # installed separately because it needs Tesseract too
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError("OCR Python packages unavailable") from exc
    if not shutil.which("tesseract"):
        raise RuntimeError("Tesseract executable unavailable")

    text_pages: list[str] = []
    for page_no in range(1, page_count + 1):
        image = convert_from_path(str(pdf), dpi=300, first_page=page_no, last_page=page_no)[0]
        text_pages.append(clean_text(pytesseract.image_to_string(image)))
    return text_pages


def needs_ocr(pages: list[str]) -> bool:
    """Treat a document with nearly no selectable text as a scanned PDF."""
    nonempty = sum(bool(page.strip()) for page in pages)
    characters = sum(len(page) for page in pages)
    return bool(pages) and (characters < 80 or nonempty / len(pages) < 0.25)


def extract_pdf(pdf: Path) -> tuple[list[str], str, list[str]]:
    """Return page text, method used, and non-fatal warnings."""
    warnings: list[str] = []
    try:
        pages = extract_with_pdfplumber(pdf)
        method = "pdfplumber"
    except Exception as exc:  # continue corpus-wide if a single parser fails
        warnings.append(f"pdfplumber failed: {type(exc).__name__}: {exc}")
        try:
            pages = extract_with_pypdf(pdf)
            method = "pypdf fallback"
        except Exception as fallback_exc:
            warnings.append(f"pypdf failed: {type(fallback_exc).__name__}: {fallback_exc}")
            return [], "failed", warnings

    if needs_ocr(pages):
        warnings.append("little/no selectable text detected; attempting OCR")
        try:
            pages = ocr_pdf(pdf, len(pages))
            method += " + OCR"
        except Exception as exc:
            warnings.append(f"OCR unavailable/failed: {type(exc).__name__}: {exc}")
    return pages, method, warnings


def heading_for(line: str) -> str | None:
    """Return the concise legal identifier from a line that looks like a heading."""
    if not HEADER_RE.match(line):
        return None
    match = SECTION_ID_RE.search(line)
    return match.group(0).strip() if match else line.strip()[:100]


def split_into_pieces(pages: list[str]) -> list[Piece]:
    """Split first on legal headings, retaining exact source-page coverage."""
    pieces: list[Piece] = []
    current_lines: list[str] = []
    current_pages: list[int] = []
    current_section = ""

    def flush() -> None:
        nonlocal current_lines, current_pages
        text = clean_text("\n".join(current_lines))
        if text:
            pieces.append(Piece(text, sorted(set(current_pages)), current_section))
        current_lines, current_pages = [], []

    for page_no, page_text in enumerate(pages, start=1):
        if not page_text:
            continue
        # Contents pages repeat every section title but contain no operative text.
        # Keep them in the raw-text export, not in the retrieval index.
        heading_lines = sum(bool(heading_for(line)) for line in page_text.splitlines())
        # A contents page announces itself on its OWN line, and lists many
        # headings. Matching a bare "contents" anywhere in the body was too
        # greedy: it discarded the single page of About TKDL.pdf over the
        # ordinary phrase "the available contents of the ancient texts",
        # losing that whole document from the index.
        toc_heading = re.search(
            r"^\s*(?:ARRANGEMENT\s+OF\s+SECTIONS|TABLE\s+OF\s+CONTENTS|CONTENTS)\s*$",
            page_text, re.I | re.M,
        )
        if ((toc_heading and heading_lines >= 5)
                or (re.search(r"^\s*SECTIONS\s*$", page_text, re.I | re.M) and heading_lines >= 8)):
            flush()
            continue
        for line in page_text.splitlines():
            heading = heading_for(line)
            if heading:
                flush()
                current_section = heading
            current_lines.append(line)
            current_pages.append(page_no)
        # A page boundary is represented in text, but does not itself split a section.
        current_lines.append("")
        current_pages.append(page_no)
    flush()
    return pieces


def paragraph_windows(piece: Piece, target: int = 650, overlap: int = 50) -> Iterable[Piece]:
    """Split oversize sections at paragraphs, then sentences/words only if needed."""
    paragraphs = [clean_text(p) for p in re.split(r"\n\s*\n", piece.text) if clean_text(p)]
    if not paragraphs:
        return
    buffer: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        # Very long paragraphs are sliced only as a final fallback.
        units = [paragraph] if len(words) <= target else [" ".join(words[i:i + target]) for i in range(0, len(words), target - overlap)]
        for unit in units:
            proposed = "\n\n".join(buffer + [unit])
            if buffer and token_count(proposed) > target:
                yield Piece("\n\n".join(buffer), piece.pages, piece.section)
                tail = " ".join("\n\n".join(buffer).split()[-overlap:])
                buffer = [tail, unit] if tail else [unit]
            else:
                buffer.append(unit)
    if buffer:
        yield Piece("\n\n".join(buffer), piece.pages, piece.section)


def chunk_pieces(pieces: list[Piece]) -> list[Piece]:
    """Prefer headings, but group adjacent short legal units into useful passages."""
    structural_chunks: list[Piece] = []
    for piece in pieces:
        if token_count(piece.text) > 800:
            structural_chunks.extend(paragraph_windows(piece))
        else:
            structural_chunks.append(piece)

    # Some rules and schedules genuinely contain one-sentence clauses. Indexing
    # each alone hurts retrieval, so collect adjacent small units to ~200 tokens.
    # The combined heading value preserves every legal boundary represented.
    chunks: list[Piece] = []
    buffer: list[Piece] = []
    def flush_buffer() -> None:
        nonlocal buffer
        if not buffer:
            return
        headings = [part.section for part in buffer if part.section]
        section = "; ".join(dict.fromkeys(headings))
        pages = sorted({page for part in buffer for page in part.pages})
        chunks.append(Piece("\n\n".join(part.text for part in buffer), pages, section[:500]))
        buffer = []

    for piece in structural_chunks:
        if token_count(piece.text) >= 200:
            flush_buffer()
            chunks.append(piece)
            continue
        candidate = "\n\n".join(part.text for part in buffer + [piece])
        if buffer and token_count(candidate) > 750:
            flush_buffer()
        buffer.append(piece)
        if token_count("\n\n".join(part.text for part in buffer)) >= 200:
            flush_buffer()
    flush_buffer()
    return chunks


# Ordered most-specific first: "geographical indication" must be tested before
# the bare "design", and "drugs and cosmetics" before "drug".
SUBTYPE_MAP: list[tuple[str, str]] = [
    ("geographical indication", "geographical_indication"), ("gi ", "geographical_indication"),
    ("biological diversity", "biodiversity_abs"), ("biodiversity", "biodiversity_abs"),
    ("access and benefit", "biodiversity_abs"), ("benefit sharing", "biodiversity_abs"),
    ("patent", "patent"), ("trade mark", "trademark"), ("trademark", "trademark"),
    ("copyright", "copyright"), ("design", "design"), ("plant variet", "plant_varieties"),
    ("drugs and cosmetics", "drug_regulatory"), ("drugs & cosmetics", "drug_regulatory"),
    ("magic remedies", "drug_regulatory"),
    ("fssai", "food_regulatory"), ("food safety", "food_regulatory"),
    ("ayurveda aahar", "food_regulatory"),
    ("tkdl", "traditional_knowledge"), ("traditional knowledge", "traditional_knowledge"),
    ("pharmacopoeia", "pharmacopoeia"), ("formulary", "pharmacopoeia"),
]

# A subtype inferred from body text needs this many marker hits to be trusted,
# so that one passing cross-reference cannot capture a document.
SUBTYPE_MIN_HITS = 3


def match_subtype(text: str) -> str | None:
    """First subtype whose marker appears in `text`, or None.

    Order-sensitive by design: used for filenames, where the earliest match in
    SUBTYPE_MAP is the most specific one.
    """
    lower = text.lower()
    return next((value for key, value in SUBTYPE_MAP if key in lower), None)


def infer_subtype(text: str) -> str | None:
    """Infer a subtype from a document's own text, by marker frequency.

    Deliberately NOT first-match-wins like `match_subtype`. Position is
    meaningless in these documents: `ABS Guidelines.pdf` is a bilingual Gazette
    whose first ~47,000 characters are Devanagari, so the first English marker
    appears halfway through the file. Any head-window scan either misses it or
    has to read half the corpus to find it.

    Frequency is the robust signal instead - the subject a document actually
    concerns is the one it keeps naming. A threshold keeps a single incidental
    cross-reference (the Patents Act mentioning "biological material") from
    outvoting nothing at all.

    Only ever consulted when the FILENAME matched nothing, so it cannot override
    a confident name-based classification.
    """
    lower = " ".join(text.lower().split())
    totals: Counter[str] = Counter()
    for marker, subtype in SUBTYPE_MAP:
        hits = lower.count(marker)
        if hits:
            totals[subtype] += hits
    if not totals:
        return None
    subtype, hits = totals.most_common(1)[0]
    return subtype if hits >= SUBTYPE_MIN_HITS else None


def classify(file_name: str, folder: str, body_text: str = "") -> tuple[str, str, str]:
    """Derive regime, subtype and year for one document.

    Subtype is matched against the filename FIRST and the document's own opening
    text second. It used to be filename-only, and filenames are not reliable
    metadata: `The_Drugs_and_Cosmetics_Rules_1945.PDF` matched nothing, because
    the underscores meant the "drugs and cosmetics" marker never appeared. That
    one miss mislabelled 854 chunks - 35% of the whole corpus, including Rule
    122-E and Schedule Y, the provisions that decide the `new_drug` and
    `phytopharmaceutical` categories - as `act_subtype: "other"`.

    The practical damage was in retrieval: `CATEGORY_REGIME_HINTS` maps
    PHYTOPHARMACEUTICAL to `drug_regulatory`, so the hint boosted the 82-chunk
    *Act* and demoted the 854-chunk *Rules* that actually govern it. The hint
    pointed away from the right law, masked only because `REGIME_BOOST` is 0.0.

    Reading the document's own first pages is the fix: a statute states what it
    is in its own title, whatever the file was named on disk.
    """
    # Separators are meaningless here - underscores, hyphens and runs of spaces
    # all just join words - so normalise them away before matching.
    normalised_name = re.sub(r"[_\-\s]+", " ", file_name.lower())
    subtype = match_subtype(normalised_name)
    if subtype is None and body_text:
        subtype = infer_subtype(body_text)
    regime = FOLDER_TO_REGIME.get(folder, "other")
    year_match = re.search(r"(?:18|19|20)\d{2}", file_name)
    return regime, subtype or "other", year_match.group(0) if year_match else ""


def resolve_input(root: Path, input_dir: str, zip_path: str) -> Path:
    """Unzip when supplied; otherwise allow a pre-extracted corpus directory."""
    archive, source = root / zip_path, root / input_dir
    if archive.exists():
        if source.exists():
            shutil.rmtree(source)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(source)
        # Some archives contain a single top-level corpus directory.
        children = [p for p in source.iterdir() if p.is_dir()]
        if len(children) == 1 and any(children[0].glob("01_classification")):
            return children[0]
        return source
    if source.exists():
        return source
    raise FileNotFoundError(f"Neither archive {archive} nor input folder {source} exists")


def write_raw_text(path: Path, pages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n\n".join(f"--- PAGE {number} ---\n{text}" for number, text in enumerate(pages, 1))
    path.write_text(content + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Repo root is the parent of pipeline/, so the script works from any cwd.
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent, help="Project folder")
    parser.add_argument("--input-dir", default="data/corpus", help="Extracted PDF corpus directory")
    parser.add_argument("--zip-path", default="data/corpus.zip", help="Archive to extract when present")
    args = parser.parse_args()
    root = args.root.resolve()
    # These three are wiped and regenerated on every run, so they must stay
    # inside data/ -- never point them at a folder that holds source code.
    output = root / "data"
    raw_dir, chunks_dir, logs_dir = output / "raw_text", output / "chunks", output / "logs"
    # Idempotency: replace generated data but retain the reusable script and README.
    for folder in (raw_dir, chunks_dir, logs_dir):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)

    try:
        source = resolve_input(root, args.input_dir, args.zip_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    # Explicit, platform-independent ordering. Path.__lt__ case-folds on Windows
    # but not on Linux, so the same corpus produced different doc_id assignments
    # on different machines - and doc_id is half of chunk_id, which is our
    # citation key. Sorting on the lowercased POSIX relative path pins it.
    pdfs = sorted(
        (p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: p.relative_to(source).as_posix().lower(),
    )
    all_chunks: list[dict[str, object]] = []
    log_lines = [f"Input folder: {source}", f"PDFs discovered: {len(pdfs)}", ""]
    methods, regime_counts, ocr_or_fail = Counter(), Counter(), []
    zero_chunk_docs: list[str] = []

    for doc_number, pdf in enumerate(pdfs, start=1):
        relative = pdf.relative_to(source)
        folder = relative.parts[0] if len(relative.parts) > 1 else ""
        pages, method, warnings = extract_pdf(pdf)
        methods[method] += 1
        log_lines.append(f"[{doc_number:03d}] {relative} | {method} | pages={len(pages)}")
        for warning in warnings:
            log_lines.append(f"  WARNING: {warning}")
        if method == "failed" or warnings:
            ocr_or_fail.append(str(relative))
        if not pages:
            continue
        # Mirror folders to prevent same-name PDFs in separate regimes overwriting each other.
        write_raw_text(raw_dir / relative.with_suffix(".txt"), pages)
        # Pass the document's full text so one whose filename says nothing
        # useful can still be classified from what it actually talks about.
        regime, subtype, year = classify(
            pdf.name, folder, body_text=" ".join(pages)
        )
        act_name = pdf.stem.replace("_", " ").strip()
        doc_id = f"DOC{doc_number:03d}"
        chunks_before = len(all_chunks)
        for number, piece in enumerate(chunk_pieces(split_into_pieces(pages)), start=1):
            text = clean_text(piece.text)
            if not text:
                continue
            metadata = {
                "chunk_id": f"{doc_id}_chunk_{number:03d}", "doc_id": doc_id,
                "file_name": pdf.name, "folder": folder, "act_name": act_name,
                "regime_type": regime, "act_subtype": subtype, "jurisdiction": "international" if regime == "international_treaty" else "national",
                "year": year, "section_or_clause": piece.section or None,
                "page_number": piece.pages[0], "page_numbers": piece.pages,
                "chunk_text": text, "token_count": token_count(text),
            }
            all_chunks.append(metadata)
            regime_counts[regime] += 1

    (chunks_dir / "all_chunks.json").write_text(json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = list(all_chunks[0]) if all_chunks else ["chunk_id", "doc_id", "file_name", "folder", "act_name", "regime_type", "act_subtype", "jurisdiction", "year", "section_or_clause", "page_number", "page_numbers", "chunk_text", "token_count"]
    with (chunks_dir / "all_chunks.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in all_chunks:
            row = dict(row)
            row["page_numbers"] = ", ".join(map(str, row["page_numbers"]))
            writer.writerow(row)

        # A PDF that extracted text but produced no chunks is silent data loss.
        # The old log called that "processed" and flagged nothing, which is how
        # About TKDL.pdf went missing without anyone noticing.
        if len(all_chunks) == chunks_before:
            log_lines.append(
                f"  WARNING: {relative} extracted {len(pages)} page(s) but produced ZERO chunks"
            )
            zero_chunk_docs.append(str(relative))

    log_lines.extend(["", "SUMMARY", f"PDFs processed: {len(pdfs)}", f"Chunks created: {len(all_chunks)}", f"Methods: {dict(methods)}", f"Chunks by regime: {dict(regime_counts)}"])
    if zero_chunk_docs:
        log_lines.append("PDFs that produced NO chunks (investigate): " + "; ".join(zero_chunk_docs))
    if ocr_or_fail:
        log_lines.append("PDFs needing manual review (warnings/OCR/failure): " + "; ".join(ocr_or_fail))
    else:
        log_lines.append("PDFs needing manual review: none flagged")
    (logs_dir / "extraction_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("\n".join(log_lines[-6:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
