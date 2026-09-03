# Ayurveda IP-law RAG extraction output

Run the pipeline from this project folder with:

```bash
python3 -m pip install -r requirements.txt
python3 build_chunks.py
```

The included `corpus/` directory is the source PDF set. For a fresh archive-based run, replace it with `corpus.zip` beside `build_chunks.py` and run the same command; the script extracts the archive into `corpus/` before processing. It is idempotent: each run regenerates `01_raw_text`, `02_chunks`, and `03_logs`.

- `01_raw_text/` contains page-labelled full-text exports. Source folders are mirrored to avoid collisions between PDFs with the same filename.
- `02_chunks/all_chunks.json` is the RAG-ready JSON array. Each record has document identity, legal regime tags, a detected heading (when found), source pages, text, and an approximate token count.
- `02_chunks/all_chunks.csv` is the same material in a spreadsheet-friendly form.
- `03_logs/extraction_log.txt` records parser/OCR fallbacks, warnings, and summary counts.

Chunks are split first on standalone legal headings (sections, rules, articles, chapters, and parts). Sections exceeding roughly 800 whitespace tokens are split on paragraphs with a 50-word overlap. Documents without recognised headings stay as document/paragraph chunks and are similarly bounded only when large.

OCR is only needed for scanned PDFs. To enable it, install the Python package in `requirements.txt` and the platform-level Tesseract engine (for macOS: `brew install tesseract`).
