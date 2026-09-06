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

export type ConfidenceLevel = "high" | "moderate" | "limited";

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

export interface Citation {
  chunk_id: string;
  act_name: string;
  section: string | null;
  page: number | null;
  source_file: string | null;
  regime: string | null;
  excerpt: string;
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
  anchor_problems: string[];
  /** Aggregate of the server's local audit trail — counts only, never text. */
  audit?: {
    entries: number;
    answered?: number;
    abstained?: number;
    escalated?: number;
    citations_rejected?: number;
    path?: string;
  };
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
