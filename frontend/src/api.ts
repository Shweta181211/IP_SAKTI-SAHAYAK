import type { Answer, ComparisonResult, Health } from "./types";

// Vite proxies /api to the backend in dev; in production both sit behind one
// origin. Either way the frontend never hardcodes a host.
const BASE = "/api";

// A cold question costs three to four sequential model round trips, and on the
// free endpoint the slowest observed path (a follow-up, which adds a
// contextualisation call) took ~30s. This is set well above that so a genuinely
// slow answer is never cut off, but it is finite: previously a hung backend left
// the UI spinning forever with no way back except a page reload.
export const REQUEST_TIMEOUT_MS = 90_000;

/** Thrown when the caller aborted deliberately, so the UI can stay quiet. */
export class CancelledError extends Error {
  constructor() {
    super("cancelled");
    this.name = "CancelledError";
  }
}

/** Thrown when our own timeout fired, which needs different wording to a cancel. */
export class TimeoutError extends Error {
  constructor() {
    super(
      "The server took too long to answer. It may be rate-limited upstream — please try again.",
    );
    this.name = "TimeoutError";
  }
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  // Two independent reasons to abort - the user pressing Stop, and our own
  // deadline - combined into one signal the fetch can take.
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), REQUEST_TIMEOUT_MS);
  const onExternalAbort = () => timeout.abort();
  signal?.addEventListener("abort", onExternalAbort);

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: timeout.signal,
    });
  } catch (error) {
    // An AbortError is ambiguous on its own; the caller's signal tells us which
    // of the two aborts fired, and the user should not see an error for a stop
    // they asked for.
    if (error instanceof DOMException && error.name === "AbortError") {
      throw signal?.aborted ? new CancelledError() : new TimeoutError();
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onExternalAbort);
  }

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

// The server keeps only the most recent turns and truncates the rest, so
// sending more is wasted bytes. It also used to be an outright failure: the
// schema capped the list at 8 and REJECTED anything longer, so every session
// broke with a raw validation error on its ninth question. The server no longer
// rejects, and the client no longer oversends — either fix alone would do, and
// both is right, because neither side should depend on the other's limit.
export const MAX_HISTORY_TURNS = 8;

export function askQuestion(
  question: string,
  jurisdiction: "india" | "international",
  history: string[] = [],
  signal?: AbortSignal,
  logConsent = false,
): Promise<Answer> {
  // The API is stateless; the client owns the transcript. Sending prior
  // questions lets the server resolve follow-ups like "what about trademarking
  // it?" into standalone questions before retrieving.
  return post<Answer>(
    "/query",
    {
      question,
      jurisdiction,
      history: history.slice(-MAX_HISTORY_TURNS),
      log_consent: logConsent,
    },
    signal,
  );
}

export function compareCategories(
  product: string,
  signal?: AbortSignal,
  logConsent = false,
): Promise<ComparisonResult> {
  return post<ComparisonResult>("/compare", { product, log_consent: logConsent }, signal);
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
