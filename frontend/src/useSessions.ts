import { useCallback, useEffect, useRef, useState } from "react";
import type { Answer, ComparisonResult } from "./types";

/**
 * Named, resumable consultations, persisted per browser.
 *
 * Why this exists beyond looking like a real tool: the backend is stateless and
 * the client owns the transcript, so "which conversation am I in" was previously
 * a single anonymous blob that "End session" destroyed. Keeping several named
 * ones lets a user park a thread and come back, and it nudges people to start a
 * fresh one for a new subject.
 *
 * It is NOT a fix for anything in the gate. TEST_RESULTS.md attributed the
 * false "we hold no trademark law" refusals to long histories; that turned out
 * to be wrong (history never reaches the gate) and the real causes are fixed in
 * retrieval.py. tests/test_gate_scope.py asserts the trademark and copyright
 * questions answer correctly ten turns deep, so nothing here is load-bearing
 * for correctness.
 *
 * Scope note: localStorage is per-browser. A real multi-device product would
 * persist sessions server-side, keyed to an account, which would also let the
 * audit log tie a question to a thread. That is deliberately not built here.
 */

/** One exchange in a transcript. Either an answer or a comparison. */
export interface Turn {
  id: number;
  kind: "answer" | "comparison";
  answer?: Answer;
  comparison?: ComparisonResult;
}

export interface Session {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  turns: Turn[];
}

const KEY = "ipsakti.sessions.v1";
/** The pre-sessions transcript, migrated once so nobody loses what they had open. */
const LEGACY_KEY = "ipsakti.turns.v2";

const MAX_SESSIONS = 20;
const MAX_TURNS_PER_SESSION = 20;
const TITLE_CHARS = 34;

interface Stored {
  activeId: string;
  sessions: Session[];
}

function newId(): string {
  return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

export function blankSession(): Session {
  const now = Date.now();
  return { id: newId(), title: "", createdAt: now, updatedAt: now, turns: [] };
}

/**
 * The first question, trimmed to fit — never a model-generated summary.
 *
 * A generated title costs a round trip, can be wrong, and would be one more
 * piece of unvalidated model text in a product whose whole claim is that its
 * text is checked. The questions here are already self-describing.
 */
export function titleFor(session: Session): string {
  if (session.title) return session.title;
  const first = session.turns[0];
  const text =
    first?.kind === "comparison"
      ? first.comparison?.product
      : first?.answer?.question;
  if (!text) return "";
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > TITLE_CHARS ? `${clean.slice(0, TITLE_CHARS).trimEnd()}…` : clean;
}

/** "today" / "yesterday" / "3 Sep" — enough to locate a thread, no clutter. */
export function relativeDay(ts: number, lang: "en" | "hi" = "en"): string {
  const then = new Date(ts);
  const today = new Date();
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(today) - startOf(then)) / 86_400_000);
  if (days <= 0) return lang === "hi" ? "आज" : "today";
  if (days === 1) return lang === "hi" ? "कल" : "yesterday";
  return then.toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", {
    day: "numeric",
    month: "short",
  });
}

function load(): Stored {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Stored;
      if (Array.isArray(parsed?.sessions) && parsed.sessions.length) {
        return parsed;
      }
    }
    // One-time migration: fold an existing transcript into a first session
    // rather than silently dropping the conversation someone had open.
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      const turns = JSON.parse(legacy) as Turn[];
      if (Array.isArray(turns) && turns.length) {
        const session: Session = {
          ...blankSession(),
          turns,
          createdAt: turns[0]?.id ?? Date.now(),
          updatedAt: Date.now(),
        };
        return { activeId: session.id, sessions: [session] };
      }
    }
  } catch {
    /* private windows and quota failures both land here; start clean */
  }
  const fresh = blankSession();
  return { activeId: fresh.id, sessions: [fresh] };
}

export function useSessions() {
  const [state, setState] = useState<Stored>(load);
  // Avoid writing back the exact state we just read on mount.
  const hydrated = useRef(false);

  useEffect(() => {
    if (!hydrated.current) {
      hydrated.current = true;
      return;
    }
    try {
      const trimmed: Stored = {
        activeId: state.activeId,
        sessions: state.sessions
          .slice(-MAX_SESSIONS)
          .map((s) => ({ ...s, turns: s.turns.slice(-MAX_TURNS_PER_SESSION) })),
      };
      localStorage.setItem(KEY, JSON.stringify(trimmed));
      // The migration is done; stop the legacy blob shadowing it.
      localStorage.removeItem(LEGACY_KEY);
    } catch {
      /* over quota or blocked - the session still works in memory */
    }
  }, [state]);

  const active =
    state.sessions.find((s) => s.id === state.activeId) ?? state.sessions[0] ?? blankSession();

  const setTurns = useCallback((update: Turn[] | ((prev: Turn[]) => Turn[])) => {
    setState((prev) => {
      const current =
        prev.sessions.find((s) => s.id === prev.activeId) ?? prev.sessions[0];
      if (!current) return prev;
      const next = typeof update === "function" ? update(current.turns) : update;
      return {
        ...prev,
        sessions: prev.sessions.map((s) =>
          s.id === current.id
            ? { ...s, turns: next, updatedAt: Date.now(), title: s.title || "" }
            : s,
        ),
      };
    });
  }, []);

  /** Start a fresh thread. Reuses an untouched one rather than stacking blanks. */
  const startSession = useCallback(() => {
    setState((prev) => {
      const empty = prev.sessions.find((s) => s.turns.length === 0);
      if (empty) return { ...prev, activeId: empty.id };
      const session = blankSession();
      return { activeId: session.id, sessions: [...prev.sessions, session] };
    });
  }, []);

  const openSession = useCallback((id: string) => {
    setState((prev) => ({ ...prev, activeId: id }));
  }, []);

  const removeSession = useCallback((id: string) => {
    setState((prev) => {
      const remaining = prev.sessions.filter((s) => s.id !== id);
      if (!remaining.length) {
        const session = blankSession();
        return { activeId: session.id, sessions: [session] };
      }
      return {
        activeId: prev.activeId === id ? remaining[remaining.length - 1].id : prev.activeId,
        sessions: remaining,
      };
    });
  }, []);

  /** Newest first, and never show the empty thread you are already sitting in. */
  const listed = [...state.sessions]
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .filter((s) => s.turns.length > 0 || s.id === state.activeId);

  return {
    sessions: listed,
    activeId: active.id,
    turns: active.turns,
    setTurns,
    startSession,
    openSession,
    removeSession,
  };
}
