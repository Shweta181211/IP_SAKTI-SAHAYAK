import type { ReactNode } from "react";

/**
 * The masthead of a content page: title, standfirst, and the mark.
 *
 * Three pages had built this three times, which is how the title and the
 * standfirst came to be capped differently on each of them. One component,
 * one measure.
 *
 * **It sets itself on arrival, in the order a sheet is actually printed.**
 * The title is wiped in from the left - ink laid across the line, not a box
 * sliding up from below - then the rule beneath it is ruled, then the
 * standfirst, then the mark is drawn into the space the standfirst leaves.
 * Four beats, about a second, once per page. Everything else on these pages
 * stays still until the reader does something.
 *
 * The mark is the letterhead device, and it is where it is for a reason: the
 * title now runs the full content width but the standfirst is held to 62
 * characters, so there is real empty space to its right on every one of these
 * pages. That space is what the mark fills. It is drawn as an outline at very
 * low contrast and it is `aria-hidden` - it carries no information, it gives
 * the block a lower-right corner.
 */
export function PageHead({
  title,
  children,
}: {
  title: ReactNode;
  children: ReactNode;
}) {
  return (
    <header className="page-head">
      <h1 className="explore-page-title">{title}</h1>
      <p className="page-lead">{children}</p>
      <svg className="page-head-mark" viewBox="0 0 40 52" aria-hidden focusable="false">
        {/* The same two mirrored curves as the logo and the support readout,
            so every leaf in this product is one shape. `pathLength` normalises
            the outline to 100 units, so the draw does not have to be retimed
            if the geometry is ever adjusted. */}
        <path d="M20 4 C7 19 7 34 20 48 C33 34 33 19 20 4 Z" pathLength={100} />
        <path d="M20 8 V46" pathLength={100} />
        <path d="M20 20 L28 15 M20 20 L12 15 M20 30 L29 24 M20 30 L11 24" pathLength={100} />
      </svg>
    </header>
  );
}
