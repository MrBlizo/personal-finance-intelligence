// A tiny, safe calculator for amount fields: "12.50+3", "3*4,50",
// "(100-20)/2" or "1'250". No eval(): a small recursive-descent parser.

/** Return the value of ``text`` rounded to cents, or null if it is not a
 *  valid number or sum. */
export function evalAmount(text: string): number | null {
  const src = text.replace(/['’\s]/g, "").replace(/,/g, ".")
    .replace(/[×x]/g, "*").replace(/÷/g, "/").replace(/−/g, "-");
  if (!src) return null;
  let i = 0;
  const peek = () => src[i];
  const number = (): number | null => {
    const m = /^\d*\.?\d+|^\d+\./.exec(src.slice(i));
    if (!m) return null;
    i += m[0].length;
    return parseFloat(m[0]);
  };
  const factor = (): number | null => {
    if (peek() === "-") { i++; const v = factor(); return v === null ? null : -v; }
    if (peek() === "+") { i++; return factor(); }
    if (peek() === "(") {
      i++;
      const v = expr();
      if (peek() !== ")") return null;
      i++;
      return v;
    }
    return number();
  };
  const term = (): number | null => {
    let v = factor();
    while (v !== null && (peek() === "*" || peek() === "/")) {
      const op = src[i++];
      const r = factor();
      if (r === null || (op === "/" && r === 0)) return null;
      v = op === "*" ? v * r : v / r;
    }
    return v;
  };
  const expr = (): number | null => {
    let v = term();
    while (v !== null && (peek() === "+" || peek() === "-")) {
      const op = src[i++];
      const r = term();
      if (r === null) return null;
      v = op === "+" ? v + r : v - r;
    }
    return v;
  };
  const v = expr();
  if (v === null || i !== src.length || !Number.isFinite(v)) return null;
  return Math.round(v * 100) / 100;
}

/** True when the text is a calculation rather than a plain number. */
export const isFormula = (text: string) => /\d\s*[-+*/×÷x]\s*[\d(]/.test(text.trim().replace(/^-/, ""));
