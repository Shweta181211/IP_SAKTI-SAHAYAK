import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Workspace from "./App";
import { fetchHealth } from "./api";
import { ExportPage } from "./pages/Export";
import { Home } from "./pages/Home";
import { SourcesPage } from "./pages/Sources";
import { TreatiesPage } from "./pages/Treaties";
import { Shell } from "./Shell";
import type { UiLang } from "./i18n";
import type { Health } from "./types";

// These three preferences are read on every page, not only inside the
// workspace, so they are owned here and handed down through the Shell context.
// Keeping a second copy inside App would give the header and the rail two
// sources of truth for the same toggle.
const UI_LANG_KEY = "ipsakti.uilang.v1";
const CONSENT_KEY = "ipsakti.logconsent.v1";

/** Carry the query string across a redirect, so /consult?q=... still boots. */
function PreserveSearch({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={{ pathname: to, search }} replace />;
}

export function Root() {
  const [uiLang, setUiLang] = useState<UiLang>(() => {
    try {
      return (localStorage.getItem(UI_LANG_KEY) as UiLang) || "en";
    } catch {
      return "en";
    }
  });
  const [logConsent, setLogConsent] = useState<boolean>(() => {
    try {
      return localStorage.getItem(CONSENT_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [health, setHealth] = useState<Health | null>(null);
  const [healthChecked, setHealthChecked] = useState(false);

  // One health call for the whole session. The workspace needs it to know
  // whether the international corpus is loaded; the header needs it for the
  // status dot. Fetching it per page would ask the same question four times.
  useEffect(() => {
    fetchHealth().then((h) => {
      setHealth(h);
      setHealthChecked(true);
    });
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(UI_LANG_KEY, uiLang);
    } catch {
      /* a remembered preference is a convenience, never a requirement */
    }
    document.documentElement.lang = uiLang;
  }, [uiLang]);

  useEffect(() => {
    try {
      localStorage.setItem(CONSENT_KEY, String(logConsent));
    } catch {
      /* same */
    }
  }, [logConsent]);

  return (
    <Shell value={{ uiLang, setUiLang, logConsent, setLogConsent, health, healthChecked }}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/ask" element={<Workspace lockedMode="ask" />} />
        <Route path="/consult" element={<PreserveSearch to="/ask" />} />
        <Route path="/compare" element={<Workspace lockedMode="compare" />} />
        <Route path="/export" element={<ExportPage />} />
        <Route path="/treaties" element={<TreatiesPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
