# IP-SAKTI Sahayak — Complete Project Brief
### For project folder. Contains: full official PS, our plan, tech stack, phases, testing criteria.

---

## PART A — OFFICIAL PROBLEM STATEMENT (Full Text, Verbatim)

**Title:** IP-SAKTI Sahayak — a multilingual, RAG-based (source-cited) AI assistant for Intellectual Property and regulatory guidance in Ayurveda, across national and international regimes.

### Background

Ayurveda rests on a vast corpus of codified and community-held traditional knowledge (TK) and on therapeutics derived from plant, microbial and animal sources. Protecting and commercialising an Ayurvedic product means navigating several overlapping regimes at once: patents, geographical indications (GI), trademarks, copyright, designs, trade secrets and plant-variety rights; the Access-and-Benefit-Sharing duties that flow from India's sovereignty over its biological resources; and the drug-regulatory framework that decides whether a formulation is a classical medicine, a proprietary medicine, a new drug, a phytopharmaceutical, a food or a cosmetic. Practitioners, researchers, AYUSH startups and MSMEs and cultivators routinely struggle with this. The result is twofold: legitimate Ayurvedic innovation is under-protected and under-commercialised, while India's traditional knowledge remains exposed to misappropriation abroad. Recent shifts — the 2024 patent and biodiversity rules, the WIPO Treaty on Genetic Resources and Associated Traditional Knowledge (2024) and a fast-moving advertising and regulatory landscape — make authoritative, plain-language guidance more necessary than ever, yet no such tool exists for the AYUSH community.

### Description

The assistant answers IPR questions specific to Ayurveda with accuracy, source citation and jurisdictional clarity, keeping the national and the international layers distinct through an explicit jurisdiction switch so that answers are never conflated.

Because intellectual property for an Ayurvedic product is inseparable from how the product is regulated, the assistant first helps classify the formulation. It asks the minimum clarifying questions to determine whether the product is a classical/generic medicine (formulation and method drawn from a First-Schedule authoritative text), a patent-or-proprietary medicine, a new or non-classical drug requiring proof of safety and effectiveness, a phytopharmaceutical, an Ayurveda-Aahar / nutraceutical, or a cosmetic — and then states what each category requires and its very different IP and ABS posture. For example, a classical formulation is largely traditional knowledge that faces the Section 3(p) patenting bar and is defended through the Traditional Knowledge Digital Library, whereas a new drug gains genuine patent potential but must generate clinical evidence.

National coverage spans the Patents Act (and the 2024 Rules), the GI, Trade Marks, Designs, Copyright and Plant-Variety regimes, the Biological Diversity Act (as amended in 2023, with the 2024 Rules) and the allied drug, advertising, labelling and food/cosmetic regimes — the Drugs and Cosmetics Act, the Drugs and Magic Remedies (Objectionable Advertisements) Act and the FSSAI Ayurveda-Aahar regulations. International coverage separately spans TRIPS, the Convention on Biological Diversity and the Nagoya Protocol, the WIPO GRATK Treaty, the PCT, the Madrid and Hague systems, the Budapest Treaty (for micro-organism deposits) and the herbal-product market-access regimes of key export markets.

The assistant also facilitates access to authoritative sources — free official databases directly and the user's own paid subscriptions only with explicit, logged permission — so that a user can move from a question to the right registry, record or form. It must cite the specific statute, rule, treaty article or record it relies on; clearly state that it provides information and not legal advice; keep its corpus current as the law changes; and never fabricate authority.

### Expected Solution

A deployable, multilingual assistant built on retrieval-augmented generation grounded in a curated, version-tracked corpus of statutes, rules, treaties, pharmacopoeial standards, registry records and case law, so that every answer is traceable to a source and hallucination is minimised. The solution should provide: a jurisdiction toggle (India vs international) with the two answer-sets kept visibly separate; routing across IP types together with the formulation-classification flow; an ABS-compliance helper and a TKDL / prior-art pointer; mandatory source citations with a confidence indicator and a path to escalate to a human IP facilitator; multilingual delivery (leveraging national language infrastructure such as Bhashini); and guardrails, a standing 'information, not legal advice' disclaimer and privacy, audit and security aligned to the Digital Personal Data Protection regime and to recognised AI-application standards. A relational knowledge graph and agentic, multi-source orchestration deepen multi-step reasoning and the build can be staged — a citation-grounded retrieval MVP first, then the graph and agentic layers, then paid-source connectors and the full multilingual and voice experience. The output should be evaluable on answer accuracy, citation correctness, safe abstention on out-of-scope or uncertain queries and multilingual quality.

### "Smallest thing that wins the room" (official benchmark example)

Ask whether a classical churna from a First Schedule text can be patented, and get an answer that first classifies the formulation, then explains the Section 3(p) bar with the statute cited and the TKDL defensive route named, and finally shows how the international answer differs when the jurisdiction is switched.

### Official Dataset Sources (as given)

- Traditional Knowledge Digital Library (TKDL) — tkdl.res.in
- Statutes & rules — India Code, indiacode.nic.in
- IP India public databases (patents/InPASS, trade marks, designs, GI Registry) — ipindia.gov.in
- National Biodiversity Authority / ABS — nbaindia.org

---

## PART B — Our Corpus (Already Collected)

```
corpus/
├── 01_classification/       (Drugs & Cosmetics Act+Rules, FSSAI Ayurveda Aahar Regulations)
├── 02_national_statutes/    (Patents Act 1970, Patents Rules 2024, GI Act 1999, Trade Marks Act 1999,
│                              Designs Act 2000, Copyright Act 1957, Plant Varieties Act, Biological
│                              Diversity Act 2002 + 2023 Amendment, Biological Diversity Rules 2024,
│                              Drugs and Magic Remedies Act)
├── 03_international/        (empty for now — added in a later phase)
├── 04_registries/           (TKDL: About/Access Policy/Access Agreement; IP India: Manual of Patent
│                              Office Practice, GI Journal examples; NBA/ABS: ABS Guidelines,
│                              Biological Diversity Rules 2024 & Amendment Rules 2025)
└── 05_pharmacopoeia/        (Ayurvedic Pharmacopoeia of India Vol-I, Ayurvedic Formulary of India)
```

---

## PART C — MVP Scope (What We Build First — Non-Negotiable Core)

**The Core Loop:**
```
User question
  → Classify formulation into 1 of 6 categories (ask clarifying Q if unclear)
  → Retrieve relevant chunks from corpus (jurisdiction-filtered)
  → Generate a 4-step reasoning trail (Classification → Legal position →
     Protection/action route → Jurisdiction note), each step citation-backed
  → Display with visible citation cards + "information, not legal advice" disclaimer
```

**Explicitly deferred to later phases (per the brief's own staging permission):**
- International jurisdiction (toggle visible, disabled for now)
- Multilingual/Bhashini
- Confidence indicator, human-facilitator escalation
- Knowledge graph, agentic orchestration
- PDF export of consultation, TKDL similarity-flag feature (build only after core loop is solid)

---

## PART D — Tech Stack

| Layer | Tool | API Key? |
|---|---|---|
| Backend | Python + FastAPI | No |
| Vector DB | ChromaDB (local) | No |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (local) | No |
| Generation | Claude API (`claude-sonnet-4-6`) | **Yes** — console.anthropic.com |
| Translation (later phase) | Bhashini API | Yes — bhashini.gov.in |
| Frontend | React + Tailwind | No |
| Hosting (demo) | Vercel (frontend) + Railway/Render (backend) | No (free tier) |

---

## PART E — Phases (for Claude Code / task breakdown)

| Phase | Deliverable | Depends on |
|---|---|---|
| 1 | Corpus processing script run successfully — vector DB populated, verified with a manual test query | Corpus PDFs collected (done) |
| 2 | Classification function working standalone — given a question, returns correct 1-of-6 category | Phase 1 |
| 3 | Retrieval function working — given a question, returns relevant chunks with correct jurisdiction filter | Phase 1 |
| 4 | Generation function working — given classification + retrieved chunks, returns structured 4-step reasoning trail JSON with real citations, no hallucination | Phases 2 & 3 |
| 5 | Backend API (FastAPI) exposing `/query`, `/classify`, `/health` endpoints wrapping the above | Phase 4 |
| 6 | Frontend chat UI — input box, chat history, jurisdiction toggle (national only enabled) | Independent, can run parallel to Phases 1-5 |
| 7 | Frontend reasoning-trail + citation-card components (static, mock data) | Independent, can run parallel |
| 8 | Frontend connected to real backend API — live end-to-end flow | Phases 5, 6, 7 |
| 9 | Testing against the 4-5 agreed benchmark queries (including the official churna example) — fix inaccuracies | Phase 8 |
| 10 | Polish — loading states, error handling, disclaimer text, demo rehearsal | Phase 9 |

**Rule: Do not start a later phase until the one it depends on is verifiably working. No skipping ahead "to save time" — it costs more time later in broken integration.**

---

## PART F — Testing / Benchmark Queries (Agree on these with the team)

1. **(Official benchmark)** "Can a classical churna from a First Schedule text be patented?" — expected: classify as classical/generic → cite Section 3(p) → name TKDL as the defensive route
2. "How do I register a Geographical Indication for an Ayurvedic product?" — expected: cite GI Act 1999 process
3. "What is Access and Benefit Sharing and when do I need NBA approval?" — expected: cite Biological Diversity Act / NBA guidelines
4. "Is my new herbal extract formulation patentable?" — expected: classify as new/non-classical drug → explain this DOES have patent potential (contrast with churna example) → note clinical evidence requirement
5. "What counts as a phytopharmaceutical under Indian law?" — expected: cite the phytopharmaceutical definition/provisions

**Success criteria per query:** correct classification, correct citation (real source name, not invented), no hallucinated facts, clear disclaimer shown.

---

## PART G — Team Roles

- **Person A (Backend):** Phases 1–5, 9 (testing backend accuracy)
- **Person B (Frontend):** Phases 6–8, 9 (testing UI/UX), 10 (polish)
- **Both:** Phase 9 integration testing, Phase 10 demo rehearsal
