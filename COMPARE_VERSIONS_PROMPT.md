# Claude Code — Compare Two Project Versions
### Paste this into Claude Code. Point it at both folders/branches before running.

---

I have two versions of the same hackathon project (IP-SAKTI Sahayak) built independently by two team members:

- **My version:** D:\IP_SAKTI-SAHAYAK
- **Teammate's version:** D:\IP-SAKTI-HER

I need you to do a rigorous, honest comparison — not just "which looks nicer." Read `PROJECT_BRIEF.md` first (if present in either folder) to know what the correct target behavior is, then evaluate both versions against it.

**For each version, check and report:**

1. **Functional completeness**
   - Does it have a working backend that actually calls an LLM to generate answers, or is it showing static/mock/hardcoded data?
   - Does the classification step (6 categories) actually run, or is it stubbed?
   - Does retrieval actually query a real vector database built from our corpus, or is it fake?
   - Are citations real (traceable to actual corpus documents) or invented/hardcoded strings?

2. **Correctness against the official PS benchmark**
   - Run this exact test query on both (if each has a working backend): "Can a classical churna from a First Schedule text be patented?"
   - Does the answer correctly classify it, cite Section 3(p) of the Patents Act, name TKDL as the defensive route, and is the reasoning trail structured as separate steps (not one paragraph)?
   - Try 2-3 more questions not in any test set to see how each handles unexpected input.

3. **Code quality and maintainability**
   - Is the code organized in a way that's easy to extend (e.g., adding the international jurisdiction later)?
   - Are there hardcoded values that should be config/env variables?
   - Is there any duplicate logic that should be shared?

4. **UI/UX**
   - Does the interface clearly show the reasoning trail (classification → legal position → protection route) as distinct, citation-backed steps?
   - Is it responsive, does it handle loading/error states, does it show the "informational, not legal advice" disclaimer?
   - Visual polish is a factor, but rank this LAST in importance — a good-looking UI with no working backend is worse than a plain UI with a fully working backend, for a working-prototype hackathon submission.

5. **Scope adherence**
   - Does either version include features beyond the agreed MVP scope in PROJECT_BRIEF.md Part C (e.g., international jurisdiction, multilingual)? If so, are those features actually working, or half-built and adding risk?

**Then give me:**
- A clear side-by-side verdict: which version is functionally stronger right now, and why.
- A specific recommendation: should we (a) pick one version as the base and port over specific good pieces from the other, (b) merge both, or (c) keep developing separately a bit longer? Justify with the evidence you gathered, not general impressions.
- If recommending a merge or port, list the SPECIFIC files/components worth taking from each version, not a vague "combine the best of both."

Do not just eyeball the code — actually run both versions locally (or tell me exactly what to run if you can't), test them with the same queries, and base your comparison on observed behavior, not assumptions from reading code alone.

---

## Additional Required Sections

**6. Flaws and gaps specific to MY version (be critical, don't soften this)**
Give me a dedicated, honest section listing everything wrong or incomplete in MY version specifically — not a general comparison, a critical self-audit. Include things like:
- Missing error handling (what happens on empty query, malformed input, backend down, API timeout/rate-limit)
- Missing conversation memory/context — does a follow-up question like "so how do I protect it instead?" work, or does every query get treated as fully independent with no memory of what was just discussed?
- Any hardcoded/mock data that looks real but isn't
- Any place the system might silently fail instead of showing an error
- Anything in PROJECT_BRIEF.md's MVP scope (Part C) that is NOT yet implemented
- Security issues (e.g., API key exposed in frontend code, `.env` not gitignored, CORS wide open in a way that would matter beyond hackathon scope)

**7. Dataset / vector DB completeness check**
Before comparing answer quality, verify the ingestion pipeline actually processed the full corpus correctly. For each PDF in the `corpus/` folder, check and report:
- Was text extraction successful, or did any PDF return empty/near-empty text (common with scanned/image-based PDFs that need OCR, which plain text extraction can't handle)?
- How many chunks were generated per source document — flag any source with suspiciously few chunks (may indicate partial extraction) or suspiciously many (may indicate duplicate ingestion)
- Are all folders from PROJECT_BRIEF.md Part B actually represented in the vector DB (01_classification, 02_national_statutes, 04_registries, 05_pharmacopoeia — 03_international should be empty/absent, that's expected)
- Is the `jurisdiction` metadata tag correctly set on every chunk (spot-check a sample)
- Report the total chunk count and a per-folder breakdown

If you find any PDF that failed extraction or produced no usable chunks, name it specifically so I know what to re-check or re-download.

---

## Output Format

Write your full findings to a new file called `COMPARISON_REPORT.md` in the project root (don't just print it in chat — I need a saved file). Structure it with clear headers matching the numbered sections above (1-7). After writing the file, give me a short summary in chat (a few sentences) of the single most important takeaway — not the full report repeated.

I will take screenshots of both running interfaces myself and share them separately for further review.
