"use client";
// Animates the number inside an already formatted amount ("MAD 10,843.24",
// "1 234,50 €", "49.8 %") from its previous value to the new one, keeping
// the locale's grouping and decimal marks. Text without a number, and
// readers who prefer reduced motion, get the value as is.
import { useEffect, useRef, useState } from "react";

const NUM = /-?\d[\d\s  .,'’]*\d|-?\d/;

interface Parsed { prefix: string; suffix: string; value: number; decimals: number;
  group: string; mark: string }

function parse(text: string): Parsed | null {
  const m = NUM.exec(text);
  if (!m) return null;
  const raw = m[0];
  const dec = /[.,](\d{1,2})$/.exec(raw);
  const decimals = dec ? dec[1].length : 0;
  const mark = dec ? raw[raw.length - decimals - 1] : ".";
  const whole = dec ? raw.slice(0, raw.length - decimals - 1) : raw;
  const group = /[\s  .,'’]/.exec(whole.replace(/^-/, ""))?.[0] ?? "";
  const digits = whole.replace(/[^\d-]/g, "");
  const value = Number(`${digits}.${dec ? dec[1] : "0"}`);
  if (!Number.isFinite(value)) return null;
  return { prefix: text.slice(0, m.index), suffix: text.slice(m.index + raw.length),
    value, decimals, group, mark };
}

function format(p: Parsed, v: number) {
  const neg = v < 0;
  const fixed = Math.abs(v).toFixed(p.decimals);
  const [int, frac] = fixed.split(".");
  const grouped = p.group ? int.replace(/\B(?=(\d{3})+(?!\d))/g, p.group) : int;
  return `${p.prefix}${neg ? "-" : ""}${grouped}${frac ? p.mark + frac : ""}${p.suffix}`;
}

const reduced = () => typeof window !== "undefined"
  && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** ``value`` with its number counting up (or down) over ``ms``. */
export function CountUp({ value, ms = 900 }: { value: string; ms?: number }) {
  const [shown, setShown] = useState(value);
  const from = useRef<number | null>(null);
  useEffect(() => {
    const p = parse(value);
    if (!p || reduced()) { setShown(value); from.current = p?.value ?? null; return; }
    const start = from.current ?? 0;
    from.current = p.value;
    if (start === p.value) { setShown(value); return; }
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / ms);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(k >= 1 ? value : format(p, start + (p.value - start) * eased));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return <span className="count-up" aria-label={value}><span aria-hidden>{shown}</span></span>;
}
