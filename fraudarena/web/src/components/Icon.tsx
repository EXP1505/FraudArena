// Inline stroke icons (24x24, stroke 2, round caps). Decorative unless the parent labels them.
const P: Record<string, string> = {
  shield: "M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3z",
  bell: "M6 16V11a6 6 0 1112 0v5l1.5 2h-15L6 16zM10 21h4",
  sun: "M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z",
  check: "M5 12.5l4.5 4.5L19 7.5",
  warn: "M12 3l10 18H2L12 3zM12 10v5M12 18v.5",
  play: "M7 4l13 8-13 8V4z",
  pause: "M8 5v14M16 5v14",
  reset: "M4 12a8 8 0 108-8H7M7 4L4 7l3 3",
  up: "M7 17L17 7M8 7h9v9",
  left: "M19 12H5M11 6l-6 6 6 6",
  right: "M5 12h14M13 6l6 6-6 6",
  pen: "M4 20h4L19 9l-4-4L4 16v4z",
  doc: "M7 3h8l4 4v14H7V3zM14 3v5h5M10 13h6M10 17h6",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c1-4 4-6 8-6s7 2 8 6",
  link: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3A4 4 0 0011 18.7l1-1",
  chev: "M6 9l6 6 6-6",
  spark: "M13 2L4 14h7l-1 8 9-12h-7l1-8z",
  refresh: "M20 11a8 8 0 00-14-4M4 4v4h4M4 13a8 8 0 0014 4M20 20v-4h-4",
  rollback: "M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3",
};

export default function Icon({ name, size = 20 }: { name: keyof typeof P | string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={P[name] ?? ""} />
    </svg>
  );
}
