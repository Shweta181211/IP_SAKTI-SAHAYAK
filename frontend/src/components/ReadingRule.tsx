import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

/**
 * How far down the sheet you are, drawn in the left margin.
 *
 * The reasoning trail already joins its four stations with a vertical rule
 * that is drawn downward as the argument is made. This is the same device at
 * page scale, and that is the reason it is a rule in the gutter and not the
 * bar across the top of the window that every site uses: the top bar belongs
 * to no product, and this one is already the product's own mark for "how far
 * along".
 *
 * Two conditions, both because an indicator that is always there stops being
 * read. It appears only when the page is long enough to be worth tracking,
 * and only where there is a real margin to put it in - below that it would
 * sit on the text.
 */

/* Measured against the window rather than fixed in pixels: "half a screen
   still to come" means the same thing on a laptop and on a monitor, where a
   pixel threshold would show the rule on one and not the other for the same
   page. Below it there is nothing worth tracking. */
const MIN_SCROLL_RATIO = 0.5;
/* The sheet is 78rem (1248px). Below this there is no gutter left over to
   put a rule in without it touching the first character. */
const MIN_VIEWPORT = 1330;

export function ReadingRule() {
  const [progress, setProgress] = useState(0);
  const [show, setShow] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    let frame = 0;

    const measure = () => {
      frame = 0;
      const doc = document.documentElement;
      const scrollable = doc.scrollHeight - window.innerHeight;
      if (
        scrollable < window.innerHeight * MIN_SCROLL_RATIO ||
        window.innerWidth < MIN_VIEWPORT
      ) {
        setShow(false);
        return;
      }
      setShow(true);
      setProgress(Math.min(1, Math.max(0, window.scrollY / scrollable)));
    };

    const schedule = () => {
      // Scroll fires far faster than the screen repaints; without this the
      // handler runs several times per painted frame for no visible gain.
      if (!frame) frame = requestAnimationFrame(measure);
    };

    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    // The readiness report and the answer trail both change the page height
    // long after mount, so the rule has to re-measure when they do.
    const ro = new ResizeObserver(schedule);
    ro.observe(document.body);

    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      ro.disconnect();
    };
  }, [pathname]);

  if (!show) return null;

  return (
    <div className="reading-rule no-print" aria-hidden>
      <span style={{ transform: `scaleY(${progress})` }} />
    </div>
  );
}
