"use client";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "./Theme";
import type { PlotFigure } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

// plotly.js is loaded lazily (it is large) and themed from the WinUI CSS
// variables so charts follow the Windows light/dark mode. Trace names,
// titles and category labels go through the translation layer.
type PlotlyLib = {
  react: (el: HTMLElement, data: unknown[], layout: unknown,
    config: unknown) => Promise<unknown>;
  purge: (el: HTMLElement) => void;
  register: (module: unknown) => void;
  Plots: { resize: (el: HTMLElement) => void };
};
let plotly: Promise<PlotlyLib> | null = null;
const loadPlotly = () => {
  plotly ??= Promise.all([
    import("plotly.js-dist-min"),
    import("plotly.js-locales/fr"),
    import("plotly.js-locales/ar"),
  ]).then(([m, fr, ar]) => {
    const P = (m.default ?? m) as unknown as PlotlyLib;
    P.register((fr as Any).default ?? fr);
    P.register((ar as Any).default ?? ar);
    return P;
  });
  return plotly;
};

type T = (k: string) => string;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Any = any;

function trText(s: string, t: T): string {
  const i = s.lastIndexOf(" / ");
  return i > 0 ? `${t(s.slice(0, i))} / ${s.slice(i + 3)}` : t(s);
}

function tr(v: Any, t: T): Any {
  if (typeof v === "string") return trText(v, t);
  if (v && typeof v === "object" && typeof v.text === "string") {
    return { ...v, text: trText(v.text, t) };
  }
  return v;
}

const isLabelArray = (a: Any) => Array.isArray(a) && a.length > 0
  && a.every((x: Any) => typeof x === "string" && !/^\d{4}-\d{2}/.test(x) && !/^-?[\d.,]+$/.test(x));

function translateFigure(fig: PlotFigure, t: T): PlotFigure {
  const data = fig.data.map((d: Any) => {
    const out = { ...d };
    if (out.name) out.name = t(out.name);
    // Sunburst/treemap: parents refer to ids when ids exist, so only the
    // visible labels are translated then.
    if (Array.isArray(out.labels)) out.labels = out.labels.map((x: Any) => tr(x, t));
    if (Array.isArray(out.parents) && !Array.isArray(out.ids)) {
      out.parents = out.parents.map((x: Any) => tr(x, t));
    }
    for (const k of ["x", "y"]) {
      if (isLabelArray(out[k])) out[k] = out[k].map((x: Any) => tr(x, t));
    }
    return out;
  });
  const layout: Any = { ...fig.layout };
  if (layout.title) layout.title = tr(layout.title, t);
  for (const key of Object.keys(layout)) {
    if (!/^[xy]axis\d*$/.test(key) || !layout[key]) continue;
    const ax = { ...layout[key] };
    if (ax.title) ax.title = tr(ax.title, t);
    if (isLabelArray(ax.categoryarray)) ax.categoryarray = ax.categoryarray.map((x: Any) => tr(x, t));
    if (isLabelArray(ax.ticktext)) ax.ticktext = ax.ticktext.map((x: Any) => tr(x, t));
    layout[key] = ax;
  }
  return { data, layout };
}

function themed(layout: Record<string, unknown>) {
  const css = getComputedStyle(document.documentElement);
  const text = css.getPropertyValue("--text-2").trim() || "#555";
  const grid = css.getPropertyValue("--divider").trim() || "#ddd";
  const font = css.getPropertyValue("--font").trim() || "Segoe UI";
  const axis = (a: unknown) => ({
    gridcolor: grid, zerolinecolor: grid, linecolor: grid,
    ...(a as object),
  });
  const out: Record<string, unknown> = { ...layout };
  out.font = { ...(layout.font as object), color: text, family: font, size: 12 };
  for (const key of Object.keys(layout)) {
    if (/^[xy]axis\d*$/.test(key)) out[key] = axis(layout[key]);
  }
  out.xaxis = axis(layout.xaxis);
  out.yaxis = axis(layout.yaxis);
  out.paper_bgcolor = "rgba(0,0,0,0)";
  out.plot_bgcolor = "rgba(0,0,0,0)";
  out.autosize = true;
  return out;
}

export default function Plot({ figure, height = 320 }: {
  figure: PlotFigure | null | undefined; height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { t, lang } = useI18n();
  const { dark: scheme } = useTheme();
  useEffect(() => {
    const el = ref.current;
    if (!el || !figure) return;
    let alive = true;
    let ro: ResizeObserver | null = null;
    const fig = translateFigure(figure, t);
    loadPlotly().then((P) => {
      if (!alive) return;
      P.react(el, fig.data, { ...themed(fig.layout), height }, {
        displaylogo: false, responsive: true, displayModeBar: "hover", locale: lang,
        modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
      });
      ro = new ResizeObserver(() => P.Plots.resize(el));
      ro.observe(el);
    });
    return () => { alive = false; ro?.disconnect(); };
  }, [figure, height, scheme, t, lang]);
  useEffect(() => () => {
    const el = ref.current;
    if (el && plotly) plotly.then((P) => P.purge(el));
  }, []);
  return <div ref={ref} className="plot" style={{ minHeight: height }} />;
}
