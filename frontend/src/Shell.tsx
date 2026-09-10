import { createContext, useContext, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { PointerAura } from "./components/PointerAura";
import { ReadingRule } from "./components/ReadingRule";
import { STRINGS, type UiLang } from "./i18n";
import type { Health } from "./types";

/** The surface every page is drawn on. Not a theme in the usual sense: no
 *  content changes, only what it is drawn on. */
export type Surface = "paper" | "dark";

export interface ShellValue {
  uiLang: UiLang;
  setUiLang: (lang: UiLang) => void;
  surface: Surface;
  setSurface: (s: Surface) => void;
  logConsent: boolean;
  setLogConsent: (v: boolean) => void;
  health: Health | null;
  healthChecked: boolean;
}

const ShellContext = createContext<ShellValue | null>(null);

export function useShell(): ShellValue {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error("useShell must be used inside Shell");
  return ctx;
}

const LINKS = [
  { to: "/", key: "navHome" as const, end: true },
  { to: "/ask", key: "navConsult" as const, end: false },
  { to: "/export", key: "navExport" as const, end: false },
  { to: "/treaties", key: "navTreaties" as const, end: false },
  { to: "/sources", key: "navSources" as const, end: false },
];

export function Shell({
  value,
  children,
}: {
  value: ShellValue;
  children: ReactNode;
}) {
  const t = STRINGS[value.uiLang];
  const statusReady = value.healthChecked && !!value.health;
  const statusError = value.healthChecked && !value.health;
  const location = useLocation();
  const onExplore = location.pathname === "/";
  const dark = value.surface === "dark";

  return (
    <ShellContext.Provider value={value}>
      <PointerAura />
      {/* Not on the landing page: that is a composition of full-height
          sections you move THROUGH, not a sheet you read down. */}
      {!onExplore && <ReadingRule />}
      <div
        // The landing page is a fixed composition, not a switchable surface:
        // its hero is dark and its garden section is deliberately light, with
        // its own cream ground. Applying the dark tokens there turned that
        // section's ink into cream ON cream - text present, contrast gone. It
        // keeps its own design in both modes.
        className={`min-h-screen ${onExplore ? "explore-root" : ""} ${
          dark && !onExplore ? "surface-dark" : ""
        }`}
      >
        {/* Two slowly drifting washes plus a pointer-tracked one. A dark
            surface that does not move looks switched off. Inert on paper,
            and skipped entirely on the landing page, which brings its own. */}
        {dark && !onExplore && (
          <>
            <div className="surface-wash" aria-hidden />
          </>
        )}
        <header className="no-print sticky top-0 z-30 border-b border-white/5 bg-[#0e1712]/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-sheet items-center justify-between gap-4 px-5 py-3">
            <NavLink to="/" className="group flex items-center gap-3">
              <svg className="h-8 w-8 text-haldi" viewBox="0 0 32 32" aria-hidden>
                <circle cx="16" cy="16" r="15" fill="none" stroke="currentColor" strokeWidth="0.6" />
                <path d="M16 26 C10 18 10 10 16 8 C22 10 22 18 16 26 Z" fill="currentColor" opacity="0.85" />
                <path d="M16 26 V8" fill="none" stroke="#f5eedd" strokeWidth="0.7" />
              </svg>
              <span className="font-display text-[length:var(--t-sub)] leading-none text-paper">
                IP-SAKTI <span className="text-haldi">Sahayak</span>
              </span>
            </NavLink>

            <nav className="hidden items-center gap-1 md:flex">
              {LINKS.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.end}
                  className={({ isActive }) =>
                    `rounded-full px-3 py-1.5 text-[length:var(--t-micro)] tracking-wide transition-colors ${
                      isActive
                        ? "bg-haldi text-ink"
                        : "text-paper/60 hover:bg-white/5 hover:text-paper"
                    }`
                  }
                >
                  {t[link.key]}
                </NavLink>
              ))}
            </nav>

            <div className="flex items-center gap-3">
              <span className="hidden items-center gap-1.5 sm:flex" title={statusReady ? "Backend connected" : "Backend unreachable"}>
                <span
                  className={`h-1.5 w-1.5 rounded-full status-dot ${
                    statusReady ? "bg-neem" : statusError ? "bg-clay status-dot--pending" : "bg-haldi status-dot--pending"
                  }`}
                />
                <span className="eyebrow hidden lg:inline text-paper/50">
                  {statusReady
                    ? `${value.health!.chunks_in_vector_db.toLocaleString()} ${t.statusOnline}`
                    : statusError
                      ? t.statusOffline
                      : t.statusConnecting}
                </span>
              </span>
            {/* One control for one preference, in one place - the Consult
                page used to carry its own copy. */}
            <div
              className="surface-switch"
              role="radiogroup"
              aria-label="Surface"
              title="Surface — Shift+D"
            >
              {(["paper", "dark"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  role="radio"
                  aria-checked={value.surface === s}
                  aria-label={s === "paper" ? "Paper surface" : "Dark surface"}
                  onClick={() => value.setSurface(s)}
                  className={`surface-switch-btn ${value.surface === s ? "is-on" : ""}`}
                >
                  {s === "paper" ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path d="M6 3h8l4 4v14H6z" strokeLinejoin="round" />
                      <path d="M14 3v4h4" strokeLinejoin="round" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path
                        d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </button>
              ))}
            </div>

            <div className="flex overflow-hidden rounded-full border border-white/15">
                {(["en", "hi"] as const).map((lang) => (
                  <button
                    key={lang}
                    type="button"
                    onClick={() => value.setUiLang(lang)}
                    className={`px-2.5 py-1 text-[length:var(--t-micro)] font-semibold ${
                      value.uiLang === lang ? "bg-haldi text-ink" : "text-paper/50"
                    }`}
                  >
                    {lang === "en" ? "EN" : "हिं"}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto border-t border-white/5 px-4 py-2 md:hidden">
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `shrink-0 rounded-full px-3 py-1 text-[length:var(--t-micro)] ${
                    isActive ? "bg-haldi text-ink" : "bg-white/5 text-paper/70"
                  }`
                }
              >
                {t[link.key]}
              </NavLink>
            ))}
          </nav>
        </header>
        {children}
      </div>
    </ShellContext.Provider>
  );
}
