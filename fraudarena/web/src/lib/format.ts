// Money is integer paise everywhere in the backend; format only at the edge.
export const inr = (paise: number) => "₹" + Math.round(paise / 100).toLocaleString("en-IN");

export const inrShort = (paise: number) => {
  const r = paise / 100;
  if (r >= 1e7) return `₹${(r / 1e7).toFixed(1)}Cr`;
  if (r >= 1e5) return `₹${(r / 1e5).toFixed(1)}L`;
  if (r >= 1e3) return `₹${(r / 1e3).toFixed(r >= 1e4 ? 0 : 1)}k`;
  return `₹${Math.round(r)}`;
};

export const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;

export const short = (h: string, n = 12) => (h && h.length > n ? `${h.slice(0, n)}…` : h);

export async function getJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}
