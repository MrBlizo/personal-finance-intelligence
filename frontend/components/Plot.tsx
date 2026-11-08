"use client";
import { useEffect, useRef, useState } from "react";
import type { PlotFigure } from "@/lib/api";

// plotly.js is loaded lazily (it is large) and themed from CSS variables
// so charts follow the Windows light/dark mode.
type PlotlyLib = {
  react: (el: HTMLElement, data: unknown[], layout: unknown,
    config: unknown) => Promise<unknown>;
  purge: (el: HTMLElement) => void;
  Plots: { resize: (el: HTMLElement) => void };
};
let plotly: Promise<PlotlyLib> | null = null;
const loadPlotly = () => {
  plotly ??= import("plotly.js-dist-min").then(
    (m) => (m.default ?? m) as unknown as PlotlyLib);
  return plotly;
};

function themed(layout: Record<string, unknown>) {
  const css = getComputedStyle(document.documentElement);
  const text = css.getPropertyValue("--text").trim() || "#222";
  const grid = css.getPropertyValue("--grid").trim() || "#ddd";
  const axis = (a: unknown) => ({
    gridcolor: grid, zerolinecolor: grid, linecolor: grid,
    ...(a as object),
  });
  const out: Record<string, unknown> = { ...layout };
  out.font = { ...(layout.font as object), color: text };
  for (const key of Object.keys(layout)) {
    if (/^[xy]axis\d*$/.test(key)) out[key] = axis(layout[key]);
  }
  out.xaxis = axis(layout.xaxis);
  out.yaxis = axis(layout.yaxis);
  out.autosize = true;
  return out;
}

export default function Plot({ figure, height = 320 }: {
  figure: PlotFigure | null | undefined; height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scheme, setScheme] = useState(0);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const h = () => setScheme((s) => s + 1);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, []);
  useEffect(() => {
    const el = ref.current;
    if (!el || !figure) return;
    let alive = true;
    let ro: ResizeObserver | null = null;
    loadPlotly().then((P) => {
      if (!alive) return;
      P.react(el, figure.data, { ...themed(figure.layout), height }, {
        displaylogo: false, responsive: true,
        modeBarButtonsToRemove: ["lasso2d", "select2d"],
      });
      ro = new ResizeObserver(() => P.Plots.resize(el));
      ro.observe(el);
    });
    return () => { alive = false; ro?.disconnect(); };
  }, [figure, height, scheme]);
  useEffect(() => () => {
    const el = ref.current;
    if (el && plotly) plotly.then((P) => P.purge(el));
  }, []);
  return <div ref={ref} className="plot" style={{ minHeight: height }} />;
}
