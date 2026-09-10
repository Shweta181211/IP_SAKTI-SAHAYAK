import { useEffect } from "react";

/**
 * Turns on the leaf pointer.
 *
 * It used to do two things: swap the cursor for the leaf, and track the mouse
 * into `--mx/--my` so a gold radial wash could follow it around every page.
 * The wash is gone - a glow chasing the cursor across a legal document is
 * decoration that pulls the eye away from the thing being read, and it was
 * repainting a full-viewport gradient on every pointermove.
 *
 * The class stays, because that is what the leaf cursor hangs off.
 */
export function PointerAura() {
  useEffect(() => {
    const fine = window.matchMedia("(pointer: fine)").matches;
    if (!fine) return;
    document.documentElement.classList.add("has-aura");
    return () => document.documentElement.classList.remove("has-aura");
  }, []);

  return null;
}
