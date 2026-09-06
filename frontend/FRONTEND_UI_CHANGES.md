# Frontend UI/UX refresh — what changed

Scope: **frontend only**. Nothing under `backend/`, `data/`, `pipeline/`, or the
API contract (`src/api.ts`, `src/types.ts`) was touched — the app talks to the
same FastAPI backend exactly as before.

## 1. Visual identity restyled to match the FINAL prototype's website
- New two-pane shell: a dark ink sidebar (mode picker, jurisdiction, privacy
  toggle, interface-language switch, disclaimer) + a warm parchment main pane
  — the same "Ayurveda pharmacopoeia meets legal registry" identity as
  `IP_SAKTI-SAHAYAK_FINAL/frontend`, ported onto this project's richer React
  app instead of replacing it.
- Palette swapped from the old sepia/ochre tones to the FINAL prototype's
  deep-forest-ink + parchment + saffron/brick/sage system
  (`tailwind.config.js`, `src/index.css`). Every component still uses the
  same semantic class names (`ink`, `haldi`, `neem`, `clay`, `indigo-dye`) —
  only the hex values moved — so `AnswerView`, `ComparisonView`,
  `Confidence`, `Verdict`, `Escalate`, `ReasoningTrail`, `CitationCard` needed
  no code changes and stay visually consistent.
- Fonts switched to IBM Plex Serif / IBM Plex Sans / IBM Plex Mono, matching
  the FINAL prototype.

## 2. Microphone / voice input (new)
- `src/useVoiceInput.ts` — a small hook around the browser's native Web
  Speech API (`SpeechRecognition` / `webkitSpeechRecognition`). No backend
  key, no server round trip, no new dependency.
- Feature-detected: on browsers without support the mic button simply never
  renders, rather than showing something that would fail.
- Two buttons appear next to the composer's textarea: a mic button (tap to
  start/stop listening, pulses a ring while active) and a language toggle
  (`EN` / `हिं`) that switches recognition between `en-IN` and `hi-IN`.
  Recognised speech is appended to whatever's already typed.

## 3. Multilingual interface (new)
- `src/i18n.ts` — an English/Hindi dictionary for every piece of interface
  chrome: labels, placeholders, buttons, hints, the empty-state copy, and the
  four example prompts (each has an English and a Hindi rendition).
- A language switch lives in the sidebar. Flipping it re-renders the whole
  shell in the chosen language instantly — no reload, no lost session.
- This only affects the app's own UI text. The substance of an answer still
  comes from the backend in whatever language the question was actually
  asked in, exactly as before.

## 4. Interactivity
- Animated brand mark (the leaf motif draws itself in on load).
- Mode / jurisdiction picker cards lift and glow on hover, with a warm
  gradient wash for the selected option.
- Mic button pulses an expanding ring while listening.
- Each new question/answer turn eases into place instead of popping in.
- A hairline shimmer sweeps the Ask/Compare button on hover.
- Example chips lift on hover.
- All of the above respects `prefers-reduced-motion` (kept from the original
  app's motion discipline).

## Not changed
- Backend, retrieval pipeline, corpus, and API contract.
- The core answer-rendering components' logic (only their surrounding
  colours/fonts changed via the shared design tokens).
