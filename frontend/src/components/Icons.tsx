/**
 * Iconography for the reasoning trail and citation rail.
 *
 * Drawn here rather than pulled from a set, because the two things this product
 * is about — Ayurvedic material and Indian legal process — have no shared stock
 * vocabulary, and the generic "AI assistant" glyphs (sparkles, chat bubbles,
 * glowing orbs) actively work against the printed-opinion identity.
 *
 * Rules that keep them a family:
 *   · 20x20 viewBox, 1.25 stroke, round caps and joins — the weight of an
 *     engraved form, not a UI toolkit.
 *   · `currentColor` throughout, so each icon inherits the semantic hue of
 *     whatever it sits in. An icon never introduces a colour of its own; the
 *     four hues keep their one meaning each.
 *   · Botanical shapes are drawn with the same geometric restraint as the
 *     procedural ones, so a leaf and a set of scales read as one hand.
 *
 * Every icon is decorative — meaning always survives in adjacent text — so all
 * of them carry aria-hidden and the surrounding element supplies the label.
 */

interface IconProps {
  className?: string;
}

const base = "h-full w-full";

function Svg({ className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ?? base}
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** Step 1 — Classification. A leaf on its stem: the material being identified. */
export function LeafIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M10 17V9" />
      <path d="M10 9c0-3.3 2.2-6 6-6 0 3.9-2.6 6-6 6Z" />
      <path d="M10 12c-2.7 0-4.6-1.7-4.6-4.6 2.9 0 4.6 1.8 4.6 4.6Z" />
    </Svg>
  );
}

/** Step 2 — Legal position. Scales: the provision weighed. */
export function ScalesIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M10 4v12" />
      <path d="M5 6h10" />
      <path d="M6.5 16h7" />
      <path d="M3 11.2 5 6l2 5.2" />
      <path d="M3 11.2a2 2 0 0 0 4 0" />
      <path d="M13 11.2 15 6l2 5.2" />
      <path d="M13 11.2a2 2 0 0 0 4 0" />
    </Svg>
  );
}

/** Step 3 — Protection route. A shield with a sprout: defence of living material. */
export function ShieldLeafIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M10 3.2 15.4 5v5.2c0 3.2-2.2 5.4-5.4 6.6-3.2-1.2-5.4-3.4-5.4-6.6V5L10 3.2Z" />
      <path d="M10 13.2V9.6" />
      <path d="M10 9.6c0-1.6 1.1-2.7 2.7-2.7 0 1.7-1.1 2.7-2.7 2.7Z" />
    </Svg>
  );
}

/** Step 4 — Jurisdiction. A boundary line across a meridian: scope, not geography. */
export function BoundaryIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="10" cy="10" r="6.8" />
      <path d="M3.2 10h13.6" />
      <path d="M10 3.2c1.9 2 2.9 4.3 2.9 6.8s-1 4.8-2.9 6.8c-1.9-2-2.9-4.3-2.9-6.8S8.1 5.2 10 3.2Z" />
    </Svg>
  );
}

/** A verified citation. A seal — the mark a registry puts on a record. */
export function SealIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="10" cy="8.2" r="4.6" />
      <path d="m7.9 11.9-.9 4.5 3-1.6 3 1.6-.9-4.5" />
      <path d="m8.2 8.2 1.3 1.3 2.4-2.5" />
    </Svg>
  );
}

/** Copy to clipboard. Two leaves of paper — a document, not a UI clipboard. */
export function CopyIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M7.4 6.2V4.4a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1h-1.8" />
      <rect x="3.6" y="7.4" width="9" height="9" rx="1" />
    </Svg>
  );
}

/** Confirmation after a copy. */
export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m4.5 10.4 3.6 3.6 7.4-8" />
    </Svg>
  );
}

/** The step icon for a given trail position. */
export const STEP_ICONS = [LeafIcon, ScalesIcon, ShieldLeafIcon, BoundaryIcon] as const;

export function StepIcon({ step, className }: { step: number; className?: string }) {
  const Icon = STEP_ICONS[step - 1] ?? LeafIcon;
  return <Icon className={className} />;
}
