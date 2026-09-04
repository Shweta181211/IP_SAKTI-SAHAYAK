# Claude Code — Plan Mode Prompt
### Copy-paste this whole thing into Claude Code (in plan mode) inside your project folder.

---

I'm building "IP-SAKTI Sahayak" for a hackathon (SIH 2026, internal round). I've placed a file called `PROJECT_BRIEF.md` in this project folder — read it fully first. It contains the complete official problem statement, our corpus structure, MVP scope, tech stack, and a 10-phase build plan (Part E).

**Before doing anything else:**
1. Read `PROJECT_BRIEF.md` completely.
2. Check this repository for any existing work already done by my teammate (she may have already started backend or frontend code, or added corpus files). Give me a summary of what already exists — folder structure, what's implemented, what's stubbed, what's missing — before proposing any plan.
3. Check whether the `corpus/` folder already has processed data (a vector DB folder like `ip_sakti_vectordb`) or if that step still needs to run.

**Then, propose a plan following the 10 phases in PROJECT_BRIEF.md Part E — but adapted to whatever you find already exists in the repo.** Don't redo work that's already done correctly; flag anything that looks incomplete or inconsistent with the brief instead of silently overwriting it.

**How I want you to work with me:**
- Execute ONE phase at a time, not the whole plan in one go.
- After finishing each phase, stop and give me a short summary: what you built, what file(s) changed, how to test/verify it, and what the next phase will be.
- Wait for my confirmation before moving to the next phase — I want to review and understand each part as it's built, not get a huge pile of code at the end.
- If a phase depends on an external step I need to do myself (e.g., setting an API key, running a script manually to verify output), tell me clearly and pause there.
- Keep changes scoped to the current phase only — don't jump ahead and half-build later phases "while you're at it."

**Also important:**
- Follow the tech stack exactly as specified in PROJECT_BRIEF.md Part D — don't substitute different libraries/tools without asking me first.
- Follow the MVP scope in Part C strictly — do not add the "deferred" features (international jurisdiction, multilingual, confidence indicators, PDF export, etc.) until I explicitly tell you the core loop is confirmed working.
- When you write backend logic (classification, retrieval, generation), make sure it matches the citation-only, no-hallucination requirement from the official PS — never let the model invent a source that isn't in the corpus.
- Use the benchmark test queries in Part F to verify your own work at the end of each relevant phase — actually run them and show me the output, don't just claim it works.

**Robustness — this must work for ANY question a user asks, not just my 5 test queries:**
- The 5 benchmark queries in Part F are for verification, not the limit of what the system should handle. Do not hardcode logic, keyword-matching, or special-casing around those specific 5 questions.
- Build the classification and retrieval logic to generalize: any Ayurveda IP/regulatory question in scope should be classifiable and answerable from the corpus, and anything genuinely out of the corpus's coverage should trigger a clear "safe abstention" response (per the official PS requirement) rather than a hallucinated answer or a silent failure.
- As part of your own testing at the end of each relevant phase, don't just run my 5 benchmark queries — also try 3-4 questions I have NOT given you (edge cases, oddly phrased questions, questions slightly outside the corpus) and show me how the system behaves on those too. I want to see it handle the unexpected, not just the rehearsed cases.

**Feature ideas — you're allowed to think beyond PROJECT_BRIEF.md's explicit list, with guardrails:**
- After you've completed and I've confirmed the core MVP loop (Phases 1-5 backend, or whatever the repo's equivalent is), I want you to propose additional feature ideas — grounded in what the official PS's "Expected solution" section describes (ABS-compliance helper, TKDL/prior-art pointer, confidence indicator, knowledge graph, etc.) as well as any genuinely useful idea of your own that fits the problem statement.
- For each idea, tell me: what it does, why it's useful for THIS problem statement specifically (not generic chatbot polish), how much effort it is, and whether it needs a new API/library.
- Do NOT implement any of these proposed features until I explicitly approve which ones to build. Propose first, build after approval.
- Do not suggest anything that compromises the citation-accuracy/no-hallucination requirement — creative features are welcome, fabricated legal information is never acceptable, even as a "demo shortcut."

**Tech stack — you have room to improve on PROJECT_BRIEF.md Part D if you have a genuinely better idea:**
- The stack in Part D (FastAPI, ChromaDB, sentence-transformers, Claude API, React+Tailwind) is a solid baseline, not a hard constraint. If you believe a different library/tool/approach would make this more robust, faster to build, or better for the hackathon demo, propose the swap and explain why, before making it.
- Do not swap silently — always tell me what you're changing and why, since I need to be able to explain our stack choices to judges too.

**UI — this must NOT look like a generic AI chatbot:**
- Avoid the cliché "dark background, glowing purple/violet gradient, floating orb" AI-assistant aesthetic — it's overused and won't stand out.
- Design something distinctive that fits the actual subject matter: Ayurveda (natural, herbal, traditional) crossed with legal/regulatory clarity (structured, trustworthy, precise). Think about a visual identity that reflects both — not a generic SaaS-AI template.
- Use a real design point of view: intentional typography, a considered color palette (not default Tailwind indigo/purple), and layout choices that make the reasoning-trail and citation cards feel like the actual product, not an afterthought bolted onto a chat window.
- Show me a plan/description of the visual direction before building the full UI, so I can react to it before a lot of component work is done.

Start by giving me the "what already exists in the repo" summary and your phase-by-phase adapted plan. Do not write any code yet — wait for my go-ahead after I review the plan.
