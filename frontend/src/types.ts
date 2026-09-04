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
}

/** Display citation line. Mirrors Citation.display on the backend. */
export function citationLabel(c: Citation): string {
  const parts = [c.act_name];
  if (c.section) parts.push(c.section);
  if (c.page) parts.push(`p. ${c.page}`);
  return parts.join(", ");
}
