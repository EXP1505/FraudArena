import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";
const KEY = "fa-theme";

const read = (): Theme => {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "dark" || v === "light") return v;
  } catch { /* storage blocked: fall through */ }
  return "dark";
};

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(read);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const set = useCallback((t: Theme) => {
    setTheme(t);
    try { localStorage.setItem(KEY, t); } catch { /* ignore */ }
  }, []);
  return [theme, set];
}
