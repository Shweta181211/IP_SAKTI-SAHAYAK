# Ayurveda IP-law RAG corpus pipeline

This repository contains 26 Indian legal and regulatory PDFs relating to Ayurveda, intellectual property, traditional knowledge, biodiversity/ABS, and pharmacopoeia, together with a reproducible extraction and chunking pipeline.

## Contents

- `corpus.zip` - original 26 PDFs, grouped by regulatory regime (extract before running build_chunks.py).
- `all_chunks.json` - 2,342 RAG-ready chunks with source, page, legal section, and classification metadata.
- `all_chunks.csv` - the same chunks for spreadsheet review.
- `extraction_log.txt` - per-document extraction outcomes and summary.


## Reproduce

```bash
python3 -m pip install -r requirements.txt
python3 build_chunks.py
```

The script uses `pdfplumber` first, `pypdf` if necessary, and OCR for scanned PDFs when Tesseract is installed. It is idempotent: rerunning it regenerates the `output/` data.

## Quality notes

All 26 supplied PDFs extracted successfully with `pdfplumber`; no document needed OCR or failed. Chunks use legal headings as primary boundaries, exclude table-of-contents pages from retrieval data, and group short adjacent clauses to preserve useful context. They are approximately 200-800 tokens where the source structure permits it.
