/**
 * Entrances that fire when the element is actually reached.
 *
 * `.reveal-in` has existed since the card grids were built, and it was wired
 * to fire on MOUNT. On a page of ten treaty routes that means card ten
 * finishes its entrance about seven hundred milliseconds after load - long
 * before anyone has scrolled far enough to see it. The animation was being
 * paid for and thrown away, which is why the pages read as static.
 *
 * So one observer, started once, watches for any `.reveal-in` in the document
 * and adds `.is-in` when it enters the viewport. Nothing else changes: the
 * keyframes, the easing and the stagger are the ones already in the
 * stylesheet, so the site keeps one motion vocabulary.
 *
 * **The stylesheet hides nothing until this module says it is running.** The
 * failure mode of every scroll reveal is content that stays invisible because
 * the observer never started - a JS error, an old browser, a print. So the
 * `reveal-armed` class on <html> is the switch, set from here, and without it
 * `.reveal-in` renders exactly as it does today.
 */

const ARMED = "reveal-armed";
const IN = "is-in";
/* Far enough that a card is revealed slightly before its top edge appears,
   so the entrance is finishing as it arrives rather than starting there. */
const MARGIN = "0px 0px -12% 0px";
/* The stagger is per BATCH, not per index in the source list. A card that is
   the tenth in its grid but the first thing you scroll to should not wait
   630ms for its turn - it is the first one you reached. */
const MAX_STEP = 5;

let started = false;

export function startReveal(): void {
  if (started) return;
  started = true;

  const root = document.documentElement;

  /* No observer, no gating - show everything, exactly as before. */
  if (typeof IntersectionObserver === "undefined") return;

  const io = new IntersectionObserver(
    (entries) => {
      let step = 0;
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const el = entry.target as HTMLElement;
        /* Overrides the inline `--i` the card grids set for their source
           order. Same specificity, later write wins. */
        el.style.setProperty("--i", String(Math.min(step, MAX_STEP)));
        el.classList.add(IN);
        io.unobserve(el);
        step += 1;
      }
    },
    { rootMargin: MARGIN, threshold: 0.01 },
  );

  const watch = (el: Element) => {
    if (el.classList.contains(IN)) return;
    io.observe(el);
  };

  const sweep = (node: ParentNode) => {
    if (node instanceof Element && node.classList.contains("reveal-in")) watch(node);
    node.querySelectorAll?.(".reveal-in").forEach(watch);
  };

  root.classList.add(ARMED);
  sweep(document);

  /* Panels that arrive after an answer - the readiness report, the
     orchestration trace - are mounted long after this runs, so the set of
     things to watch is not fixed at startup. */
  new MutationObserver((records) => {
    for (const record of records) {
      record.addedNodes.forEach((n) => {
        if (n.nodeType === 1) sweep(n as Element);
      });
    }
  }).observe(document.body, { childList: true, subtree: true });

  /* Printing must never lose content to an entrance that has not run. */
  window.addEventListener("beforeprint", () => {
    root.classList.remove(ARMED);
  });
}
