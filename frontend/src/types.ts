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
  | "conversational";

export type ConfidenceLevel = "high" | "moderate" | "limited";

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
  collection: string;
  embed_model: string;
  generation_model: string;
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
