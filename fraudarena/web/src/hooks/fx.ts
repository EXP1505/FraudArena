// Small motion helpers: number count-up, scroll reveal, cursor spotlight. All respect reduced motion.
import { useEffect, useRef, useState } from "react";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Animates from the previous value to `target` (ease-out). */
export function useCountUp(target: number, ms = 800): number {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (reduced() || from.current === target) { from.current = target; setV(target); return; }
    const start = performance.now(), a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / ms), e = 1 - Math.pow(1 - k, 3);
      setV(a + (target - a) * e);
      if (k < 1) raf = requestAnimationFrame(tick); else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); from.current = target; };
  }, [target, ms]);
  return v;
}

/** Adds .reveal / .in to cards and panels as they enter the viewport, including ones rendered later. */
export function useAutoFx(routeKey: string) {
  useEffect(() => {
    if (reduced() || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) { (e.target as HTMLElement).classList.add("in"); io.unobserve(e.target); }
    }, { threshold: 0.08 });
    const seen = new WeakSet<Element>();
    let n = 0;
    const scan = () => {
      document.querySelectorAll("main .card, main .panel, main .banner, main .step, main .rule-card").forEach((el) => {
        if (seen.has(el)) return;
        seen.add(el);
        const h = el as HTMLElement;
        const r = h.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0 && n > 40) return; // do not hide what is already on screen after churn
        h.style.setProperty("--d", `${Math.min(n++ % 8, 7) * 55}ms`);
        h.classList.add("reveal");
        io.observe(h);
      });
    };
    scan();
    const mo = new MutationObserver(() => scan());
    mo.observe(document.querySelector("main") ?? document.body, { childList: true, subtree: true });
    const move = (ev: PointerEvent) => {
      const c = (ev.target as HTMLElement | null)?.closest?.(".card, .panel") as HTMLElement | null;
      if (!c) return;
      const b = c.getBoundingClientRect();
      c.style.setProperty("--mx", `${ev.clientX - b.left}px`);
      c.style.setProperty("--my", `${ev.clientY - b.top}px`);
    };
    document.addEventListener("pointermove", move, { passive: true });
    return () => { io.disconnect(); mo.disconnect(); document.removeEventListener("pointermove", move); };
  }, [routeKey]);
}
