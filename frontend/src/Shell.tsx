import { createContext, useContext, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { PointerAura } from "./components/PointerAura";
import { STRINGS, type UiLang } from "./i18n";
import type { Health } from "./types";

export interface ShellValue {
  uiLang: UiLang;
  setUiLang: (lang: UiLang) => void;
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

  return (
    <ShellContext.Provider value={value}>
      <PointerAura />
      <div className={`min-h-screen ${onExplore ? "explore-root" : ""}`}>
        <header className="no-print sticky top-0 z-30 border-b border-white/5 bg-[#0e1712]/80 backdrop-blur-md">
          <div className="mx-auto flex max-w-sheet items-center justify-between gap-4 px-5 py-3">
            <NavLink to="/" className="group flex items-center gap-3">
              <svg className="h-8 w-8 text-haldi" viewBox="0 0 32 32" aria-hidden>
                <circle cx="16" cy="16" r="15" fill="none" stroke="currentColor" strokeWidth="0.6" />
                <path d="M16 26 C10 18 10 10 16 8 C22 10 22 18 16 26 Z" fill="currentColor" opacity="0.85" />
                <path d="M16 26 V8" fill="none" stroke="#f5eedd" strokeWidth="0.7" />
              </svg>
              <span className="font-display text-[17px] leading-none text-paper">
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
                    `rounded-full px-3 py-1.5 text-[12.5px] tracking-wide transition-colors ${
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
            <div className="flex overflow-hidden rounded-full border border-white/15">
                {(["en", "hi"] as const).map((lang) => (
                  <button
                    key={lang}
                    type="button"
                    onClick={() => value.setUiLang(lang)}
                    className={`px-2.5 py-1 text-[11px] font-semibold ${
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
                  `shrink-0 rounded-full px-3 py-1 text-[12px] ${
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
