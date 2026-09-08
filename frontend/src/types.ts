/**
 * Mirrors backend/app/schemas.py exactly. If a field changes there, change it
 * here — these two files are one contract with a network in the middle.
 */

export type Category =
  | "classical_generic"
  | "patent_proprietary"
  | "new_drug"
  | "phytopharmaceutical"
  | "ayurveda_aahar"
  | "cosmetic"
  | "not_applicable"
  | "needs_clarification";

export type AbstentionKind =
  | "none"
  | "no_evidence"
  | "too_vague"
  | "foreign_jurisdiction"
  | "out_of_scope"
  | "gate_unavailable"
  | "conversational"
  | "legal_advice";

export type ConfidenceLevel = "strong" | "high" | "moderate" | "limited";

export type TakeawayIntent = "patent" | "gi" | "abs" | "tkdl" | "other";

/** The one-line orientation above the trail.
 *
 *  `label` is drawn from a closed, always-hedged vocabulary that the backend
 *  validates against `TAKEAWAY_LABELS` — a bare "yes, patentable" cannot reach
 *  the client. `reason` is citation-checked like a reasoning step. */
export interface Takeaway {
  intent: TakeawayIntent;
  label: string;
  reason: string;
  citation_ids: string[];
  unsourced: boolean;
}

/** Phrasing only. Citations and classification are identical across styles —
 *  plain mode is a rewrite of a finished answer, not a second generation. */
export type ResponseStyle = "legal" | "plain";

export interface NextStep {
  text: string;
  citation_ids: string[];
  /** Which corpus the step follows from, so a treaty-derived step can never
   *  read as an Indian requirement. */
  jurisdiction: "national" | "international";
}

export interface NextSteps {
  applicable: boolean;
  steps: NextStep[];
  reason: string | null;
  unavailable: boolean;
  rejected: string[];
  disclaimer: string;
}

export interface CategoryContrast {
  category: Category;
  label: string;
  posture: string;
  patentable: string;
  citation_ids: string[];
}

export interface ComparisonResult {
  product: string;
  contrasts: CategoryContrast[];
  citations: Citation[];
  abstained: boolean;
  abstention_message: string | null;
  search_degraded: boolean;
  degraded_reason: string | null;
  disclaimer: string;
}

/** A provision a cited passage points at, or that points at it.
 *
 *  Derived from the passage's own text by the provision graph — no model is
 *  involved, so it cannot invent a relation. It adds no claim to the answer:
 *  it is navigation, so "subject to rule 21" stops being a dead end. */
export interface RelatedProvision {
  chunk_id: string;
  act_name: string;
  provision: string;
  page: number | null;
  excerpt: string;
  /** "outbound" — this citation defers to it. "inbound" — it relies on this. */
  direction: "outbound" | "inbound";
}

/** One pipeline stage that ran to produce an answer. */
export interface TraceStep {
  stage: string;
  status: "ok" | "skipped" | "degraded";
  ms: number;
  detail: string;
}

export interface Citation {
  chunk_id: string;
  act_name: string;
  section: string | null;
  page: number | null;
  source_file: string | null;
  regime: string | null;
  excerpt: string;
  related: RelatedProvision[];
}

export interface ClassificationResult {
  category: Category;
  label: string;
  rationale: string;
  defining_source_id: string | null;
  defining_source_name: string | null;
  clarifying_question: string | null;
}

export interface ReasoningStep {
  step: number;
  title: string;
  content: string;
  citation_ids: string[];
  abstained: boolean;
}

export interface Answer {
  question: string;
  resolved_question: string | null;
  jurisdiction: string;
  headline: string | null;
  /** Sources backing the headline itself. Empty when it could not be tied
   *  to verified evidence — see `headline_unsourced`. */
  headline_citation_ids: string[];
  /** The headline is a summary, not a sourced finding. The UI must say so. */
  headline_unsourced: boolean;
  /** Null for definitional/procedural questions and every abstention. */
  takeaway: Takeaway | null;
  /** The stages that ran, in order — orchestration shown, not asserted. */
  trace: TraceStep[];
  confidence: ConfidenceLevel | null;
  confidence_label: string | null;
  confidence_score: number | null;
  confidence_reasons: string[];
  example_questions: string[];
  classification: ClassificationResult | null;
  steps: ReasoningStep[];
  citations: Citation[];
  abstained: boolean;
  abstention_kind: AbstentionKind;
  abstention_message: string | null;
  clarifying_question: string | null;
  rejected_citation_ids: string[];
  response_style?: ResponseStyle;
  /** Provision references the model wrote that no retrieved chunk contains.
   *  The sentence carrying them is removed server-side before the answer ships. */
  unsupported_provisions: string[];
  /** Offer a human IP facilitator. Set only for a real legal need this system
   *  cannot meet — never for a vague, off-topic, or transiently failed one. */
  escalate: boolean;
  escalation_reason: string | null;
  /** Retrieval ran without query expansion (upstream hiccup), so recall was
   *  narrowed. Shown to the user — it used to fail silently. */
  search_degraded: boolean;
  degraded_reason: string | null;
  disclaimer: string;
}

export interface Health {
  status: string;
  chunks_in_json: number;
  chunks_in_vector_db: number;
  /** Per-jurisdiction chunk counts; drives whether the International toggle is live. */
  chunks_by_jurisdiction?: Record<string, number>;
  collection: string;
  embed_model: string;
  generation_model: string;
  /** Active (provider:model) fallback chain, best first. */
  llm_chain?: string[];
  /** Model calls answered per endpoint since the server started. More than one
   *  entry is the failover chain having actually moved — counted on the way out
   *  of each successful call, not inferred from the configured head. */
  llm_served?: Record<string, number>;
  anchor_problems: string[];
  /** Shape of the provision graph: nodes, edges, and how much of the corpus
   *  the cross-references actually reach. */
  graph?: {
    provisions?: number;
    passages_with_references?: number;
    references?: number;
    provisions_referenced?: number;
  };
  graph_problems?: string[];
  /** Aggregate of the server's local audit trail — counts only, never text. */
  audit?: AuditSummary;
}

/** Counts over the server's audit log. Mirrors `audit.summary()`. */
export interface AuditSummary {
  entries: number;
  answered?: number;
  abstained?: number;
  escalated?: number;
  citations_rejected?: number;
  /** Rows that kept the question text, i.e. rows where the asker opted in.
   *  A count rather than a flag, so the consent default can be checked. */
  retained_question_text?: number;
  kinds?: Record<string, number>;
  abstention_kinds?: Record<string, number>;
  /** Which endpoint was at the head of the chain when each row was written.
   *  NOT which one served it — see Health.llm_served for that. */
  models?: Record<string, number>;
  first_entry?: string | null;
  last_entry?: string | null;
  path?: string;
}

/** One redacted row of the audit log. The server strips user content before
 *  serving, so every field here is operational — what was decided, not what
 *  was asked. Untyped values because the row shape differs per `kind`. */
export type AuditEntry = Record<string, string | number | boolean | null>;

export interface AuditTrail {
  summary: AuditSummary;
  entries: AuditEntry[];
  redacted_fields: string[];
  retention: string;
}

/** Display citation line. Mirrors Citation.display on the backend. */
export function citationLabel(c: Citation): string {
  const parts = [c.act_name];
  if (c.section) parts.push(c.section);
  if (c.page) parts.push(`p. ${c.page}`);
  return parts.join(", ");
}

/** One similarity or difference between the two legal systems.
 *
 *  Each side carries its own claim and its own citations. There is deliberately
 *  no field for an unattributed statement of law — the problem statement
 *  requires the two answer-sets to stay visibly separate, and a shape that
 *  cannot express a blended claim is a stronger guarantee than a prompt asking
 *  for one. */
export interface JurisdictionPoint {
  kind: "similarity" | "difference";
  summary: string;
  national_claim: string | null;
  national_citation_ids: string[];
  international_claim: string | null;
  international_citation_ids: string[];
}

export interface JurisdictionComparison {
  question: string;
  /** Independently generated — not one answer relabelled. */
  national: Answer;
  international: Answer;
  points: JurisdictionPoint[];
  /** Comparison points dropped for citing across jurisdictions or citing nothing. */
  rejected_points: string[];
  synthesis_unavailable: boolean;
  synthesis_message: string | null;
  disclaimer: string;
}

// --------------------------------------------------------------------------
// Export readiness
// --------------------------------------------------------------------------

/** Derived from what retrieval actually found, never assigned by a fixed rule.
 *  `not_covered` is forced server-side whenever an item's citations do not
 *  survive validation — an honest gap, not a failure. */
export type ReadinessStatus =
  | "verified"
  | "needs_verification"
  | "blocker"
  | "not_covered";

export interface ReadinessItem {
  /** Which requirement area this line answers. Fixed per side, so the checklist
   *  is complete: an area the corpus cannot reach still appears, marked
   *  not_covered, rather than quietly missing. */
  area?: string;
  area_label?: string;
  title: string;
  detail: string;
  status: ReadinessStatus;
  status_reason: string;
  citation_ids: string[];
}

export interface ReadinessSection {
  jurisdiction: "national" | "international";
  heading: string;
  covered: boolean;
  uncovered_reason: string | null;
  items: ReadinessItem[];
}

export interface ExportReadinessRequest {
  product: string;
  ingredients: string;
  category: Category | null;
  health_claims: boolean;
  target_country: string;
  log_consent?: boolean;
}

export interface ExportReadinessReport {
  product: string;
  target_country: string;
  classification: ClassificationResult | null;
  target_framing: string | null;
  target_framing_citation_ids: string[];
  india: ReadinessSection | null;
  target: ReadinessSection | null;
  action_plan: NextStep[];
  citations: Citation[];
  rejected_citation_ids: string[];
  confidence: ConfidenceLevel | null;
  confidence_label: string | null;
  confidence_score: number | null;
  confidence_reasons: string[];
  abstained: boolean;
  abstention_kind: AbstentionKind;
  abstention_message: string | null;
  escalate: boolean;
  escalation_reason: string | null;
  disclaimer: string;
}

