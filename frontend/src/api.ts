import type { Answer, ComparisonResult, Health } from "./types";

// Vite proxies /api to the backend in dev; in production both sit behind one
// origin. Either way the frontend never hardcodes a host.
const BASE = "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    // FastAPI puts validation errors in `detail`, sometimes as an array.
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail) && data.detail[0]?.msg)
        detail = data.detail[0].msg;
    } catch {
      /* keep the status-code message */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function askQuestion(
  question: string,
  jurisdiction: "india" | "international",
  history: string[] = [],
): Promise<Answer> {
  // The API is stateless; the client owns the transcript. Sending prior
  // questions lets the server resolve follow-ups like "what about trademarking
  // it?" into standalone questions before retrieving.
  return post<Answer>("/query", { question, jurisdiction, history });
}

export function compareCategories(product: string): Promise<ComparisonResult> {
  return post<ComparisonResult>("/compare", { product });
}

export async function fetchHealth(): Promise<Health | null> {
  try {
    const response = await fetch(`${BASE}/health`);
    if (!response.ok) return null;
    return (await response.json()) as Health;
  } catch {
    // A dead backend is an expected state during development, not an error
    // worth surfacing as a crash — the header simply shows "offline".
    return null;
  }
}
