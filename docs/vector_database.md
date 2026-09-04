# Embeddings and local vector database

This module converts the legal chunks in `data/chunks/all_chunks.json` into multilingual semantic embeddings and stores them in persistent local ChromaDB collection `ip_sakti_corpus`.

## Run

```bash
python -m pip install -r pipeline/requirements.txt
python pipeline/build_vector_db.py
python pipeline/test_retrieval.py
```

The default is `intfloat/multilingual-e5-base`: a free multilingual model supporting Hindi and many Indian languages. `BAAI/bge-m3` is higher-capacity but substantially larger; use it on a machine with enough disk/RAM via `python pipeline/build_vector_db.py --model BAAI/bge-m3 --rebuild`, then pass the same `--model` to the test script.

`build_vector_db.py` skips an existing populated database to avoid accidental re-embedding. Use `--rebuild` after changing model, chunks, or settings.

`test_retrieval.py` includes a small, explicit Hindi legal-term expansion and routes clearly identified trademark questions to the `trademark` metadata subtype before semantic ranking. This improves cross-language retrieval when the underlying legislation is English.

## Reuse from an app

Note: `test_retrieval.py` is a dev sanity tool, not app code. The backend
reimplements search in `backend/app/retrieval.py` without its keyword routing.
For ad-hoc scripts you can still import `search` from `test_retrieval.py`, load the model and collection once at application startup, then call:

```python
results = search(collection, model, model_name, user_query, regime_type="ip_statute", top_k=5)
```

Pass the returned chunk text and metadata to an LLM, instruct it to answer only from the evidence, and cite `file_name`, `section_or_clause`, and `page_number` in its final answer.

The persisted database lives at `data/vector_db/` and is gitignored - it is rebuildable
from `data/chunks/all_chunks.json` at any time.
