import { useEffect } from "react";

/** Gold ring that follows the pointer. Hidden on touch / reduced motion. */
export function PointerAura() {
  useEffect(() => {
    const fine = window.matchMedia("(pointer: fine)").matches;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!fine || reduce) return;

    const move = (e: PointerEvent) => {
      document.documentElement.style.setProperty("--mx", `${e.clientX}px`);
      document.documentElement.style.setProperty("--my", `${e.clientY}px`);
      document.documentElement.style.setProperty("--mxp", String(e.clientX / window.innerWidth));
      document.documentElement.style.setProperty("--myp", String(e.clientY / window.innerHeight));
    };
    window.addEventListener("pointermove", move, { passive: true });
    document.documentElement.classList.add("has-aura");
    return () => {
      window.removeEventListener("pointermove", move);
      document.documentElement.classList.remove("has-aura");
    };
  }, []);

  return <div className="site-aura" aria-hidden />;
}
