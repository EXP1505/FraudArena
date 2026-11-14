// Owner: M4. Login illustration: fraud attempts (left, red) run at a shield and stop; honest payments (right, green) pass through.
export default function LoginArt() {
  const attackers = [[60, 120], [40, 215], [70, 310], [50, 405]];
  const customers = [[500, 150], [520, 255], [495, 360]];
  return (
    <svg className="login-art" viewBox="0 0 560 520" role="img" aria-label="Fraud attempts stopped by a shield while honest payments pass through">
      <defs>
        <radialGradient id="la-glow" cx="50%" cy="48%" r="50%">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity=".55" />
          <stop offset="55%" stopColor="var(--accent)" stopOpacity=".10" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="la-shield" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent-hi)" /><stop offset="100%" stopColor="var(--accent)" />
        </linearGradient>
      </defs>
      <circle cx="280" cy="262" r="240" fill="url(#la-glow)" />
      {[70, 120, 175].map((r) => <circle key={r} cx="280" cy="262" r={r + 60} fill="none" stroke="var(--border)" strokeWidth="1" strokeDasharray="2 7" />)}

      {attackers.map(([x, y], i) => (
        <g key={i}>
          <path d={`M${x + 14} ${y} C ${x + 90} ${y}, 150 ${262 + (y - 262) * 0.45}, 205 ${262 + (y - 262) * 0.3}`}
                fill="none" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeDasharray="7 8" className="la-flow" opacity=".85" />
          <circle cx={x} cy={y} r="13" fill="none" stroke="var(--danger)" strokeWidth="2" />
          <circle cx={x} cy={y} r="4.5" fill="var(--danger)" />
          <g transform={`translate(205 ${262 + (y - 262) * 0.3})`} stroke="var(--danger)" strokeWidth="2.5" strokeLinecap="round"><path d="M-6 -6l12 12M6 -6l-12 12" /></g>
        </g>
      ))}

      {customers.map(([x, y], i) => (
        <g key={i}>
          <path d={`M355 ${262 + (y - 262) * 0.3} C 410 ${262 + (y - 262) * 0.5}, 440 ${y}, ${x - 16} ${y}`}
                fill="none" stroke="var(--ok)" strokeWidth="2" strokeLinecap="round" strokeDasharray="7 8" className="la-flow" opacity=".85" />
          <rect x={x - 13} y={y - 13} width="26" height="26" rx="8" fill="none" stroke="var(--ok)" strokeWidth="2" />
          <path d={`M${x - 5} ${y} l4 4 l7 -8`} fill="none" stroke="var(--ok)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      ))}

      <g transform="translate(280 262)">
        <path d="M0 -120 L92 -88 V8 C92 64 52 104 0 124 C-52 104 -92 64 -92 8 V-88 Z" fill="url(#la-shield)" stroke="var(--accent-hi)" strokeWidth="2" />
        <path d="M0 -98 L74 -72 V6 C74 52 42 84 0 101 C-42 84 -74 52 -74 6 V-72 Z" fill="var(--bg)" opacity=".86" />
        <path d="M-30 6 l22 24 l44 -52" fill="none" stroke="var(--accent-hi)" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}
