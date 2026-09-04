# Ayurveda IP-law RAG corpus pipeline

This repository contains 26 Indian legal and regulatory PDFs relating to Ayurveda, intellectual property, traditional knowledge, biodiversity/ABS, and pharmacopoeia, together with a reproducible extraction and chunking pipeline.

## Contents

- `data/corpus.zip` - original 26 PDFs, grouped by regulatory regime. `build_chunks.py` extracts it automatically.
- `data/chunks/all_chunks.json` - 2,342 RAG-ready chunks with source, page, legal section, and classification metadata.
- `data/chunks/all_chunks.csv` - the same chunks for spreadsheet review.
- `data/logs/extraction_log.txt` - per-document extraction outcomes and summary.


## Reproduce

```bash
python -m pip install -r pipeline/requirements.txt
python pipeline/build_chunks.py
```

The script uses `pdfplumber` first, `pypdf` if necessary, and OCR for scanned PDFs when Tesseract is installed. It is idempotent: rerunning it wipes and regenerates `data/raw_text`, `data/chunks`
and `data/logs`. The committed `data/chunks/all_chunks.json` is the shared artifact - you
do not need to rerun this unless the source PDFs change.

## Quality notes

All 26 supplied PDFs extracted successfully with `pdfplumber`; no document needed OCR or failed. Chunks use legal headings as primary boundaries, exclude table-of-contents pages from retrieval data, and group short adjacent clauses to preserve useful context. They are approximately 200-800 tokens where the source structure permits it.
