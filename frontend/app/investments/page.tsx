"use client";
import Link from "next/link";
import { useState } from "react";
import {
  Badge, Button, Field, Menu, MenuDivider, MenuItem, MenuList, MenuPopover,
  MenuTrigger, SpinButton, Tab, TabList, Tooltip,
} from "@fluentui/react-components";
import {
  Add20Regular, ArrowSync20Regular, MoreHorizontal20Regular, TargetArrow20Regular,
} from "@fluentui/react-icons";
import Plot from "@/components/Plot";
import { accountOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, Modal, PageHead, Section, Spinner, useLoad,
} from "@/components/ui";
import {
  Holding, Performance, PlotFigure, Trade, del, get, post, put,
} from "@/lib/api";
import { ASSET_CLASSES, CURRENCIES, date, money, num, pct, signClass, today } from "@/lib/format";
import { useT } from "@/lib/i18n";

const BLUE = "#0072B2", GREEN = "#009E73", ORANGE = "#D55E00";
const SOURCES: Record<string, string> = {
  manual: "Manual", stooq: "stooq (end of day)", coingecko: "CoinGecko (crypto)",
};

function TargetsDialog({ current, onClose, onSaved }: {
  current: Record<string, number>; onClose: () => void; onSaved: () => void;
}) {
  const t = useT();
  const [v, setV] = useState<Record<string, number>>(
    Object.fromEntries(Object.keys(ASSET_CLASSES).map((k) => [k, current[k] ?? 0])));
  const [error, setError] = useState<string | null>(null);
  const total = Object.values(v).reduce((s, x) => s + (x || 0), 0);
  return (
    <Modal title={t("Target allocation")} onClose={onClose} actions={<>
      <Button appearance="primary" disabled={total !== 0 && Math.abs(total - 100) > 0.5}
        onClick={async () => {
          try {
            const targets = Object.fromEntries(Object.entries(v).filter(([, x]) => x > 0));
            await put("/api/settings", { allocation_targets: targets });
            onSaved(); onClose();
          } catch (e) { setError((e as Error).message); }
        }}>{t("Save")}</Button>
      <Button onClick={onClose}>{t("Cancel")}</Button></>}>
      {error && <Banner kind="error">{error}</Banner>}
      <div className="caption">{t("Percent of the portfolio per asset class. Must add up to 100 %, or 0 to remove all targets.")}</div>
      <div className="form-grid">
        {Object.entries(ASSET_CLASSES).map(([k, label]) => (
          <Field key={k} label={t(label)}>
            <SpinButton min={0} max={100} step={5} value={v[k]}
              onChange={(_, d) => setV({ ...v, [k]: Number(d.value ?? d.displayValue ?? 0) || 0 })} />
          </Field>))}
      </div>
      <div className={Math.abs(total - 100) > 0.5 && total !== 0 ? "neg" : "caption"}>
        {t("Total: {v} %", { v: num(total, 0) })}</div>
    </Modal>
  );
}

export default function Investments() {
  const t = useT();
  const refs = useRefs();
  const holdings = useLoad(() => get<Holding[]>("/api/holdings"));
  const perf = useLoad(() => get<Performance>("/api/investments/performance"));
  const alloc = useLoad(() => get<PlotFigure>("/api/analytics/charts/allocation"));
  const [tab, setTab] = useState("holdings");
  const [edit, setEdit] = useState<Holding | "new" | null>(null);
  const [trade, setTrade] = useState<Holding | null>(null);
  const [price, setPrice] = useState<Holding | null>(null);
  const [history, setHistory] = useState<Holding | null>(null);
  const [remove, setRemove] = useState<Holding | null>(null);
  const [targets, setTargets] = useState(false);
  const [msg, setMsg] = useState<{ kind: "success" | "warning" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const reload = () => { holdings.reload(); perf.reload(); alloc.reload(); refs.reload(); };
  const base = refs.data?.settings.base_currency ?? "CHF";
  const invAccounts = accountOptions(refs.data?.accounts ?? [], (a) => a.type === "investment");
  const hs = holdings.data ?? [];
  const sum = (k: keyof Holding) => hs.reduce((s, h) => s + ((h[k] as number | null) ?? 0), 0);
  const value = sum("market_value_base");
  const cost = sum("cost_basis_base");
  const p = perf.data;
  const xirrOf = (id: number) => p?.holdings.find((r) => r.id === id)?.xirr ?? null;
  const online = hs.filter((h) => h.price_source !== "manual").length;

  const updatePrices = async () => {
    setBusy(true);
    try {
      const r = await post<{ updated: number; new_prices: number;
        errors: { symbol: string; error: string }[] }>("/api/prices/update");
      setMsg(r.errors.length
        ? { kind: "warning", text: r.errors.map((e) => e.error).join(" ") }
        : { kind: "success", text: t("{n} new prices for {h} holdings.", { n: r.new_prices, h: r.updated }) });
      reload();
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); }
  };

  const twrFig: PlotFigure | null = p && p.twr_months.length ? {
    data: [{ type: "bar", x: p.twr_months.map((m) => m.month),
      y: p.twr_months.map((m) => (m.return ?? 0) * 100), name: "Monthly return",
      marker: { color: p.twr_months.map((m) => ((m.return ?? 0) >= 0 ? GREEN : ORANGE)) },
      hovertemplate: "%{x}: %{y:.2f} %<extra></extra>" }],
    layout: { margin: { l: 48, r: 12, t: 8, b: 40 }, showlegend: false,
      yaxis: { title: { text: "Return / %" }, ticksuffix: " %" } },
  } : null;
  const divFig: PlotFigure | null = p && p.dividends_by_year.length ? {
    data: [{ type: "bar", x: p.dividends_by_year.map((d) => String(d.year)),
      y: p.dividends_by_year.map((d) => d.amount), name: "Dividends",
      marker: { color: BLUE }, hovertemplate: `%{x}: %{y:,.2f} ${base}<extra></extra>` }],
    layout: { margin: { l: 56, r: 12, t: 8, b: 40 }, showlegend: false,
      xaxis: { type: "category" }, yaxis: { title: { text: `Dividends / ${base}` } } },
  } : null;

  return (
    <>
      <PageHead title={t("Investments")}
        sub={t("Average-cost method · prices from stooq, CoinGecko or entered manually")}>
        <Tooltip relationship="description" content={online ? t("Download the latest prices") : t(
          "Give a holding a price source (stooq or CoinGecko) to download prices.")}>
          <Button icon={<ArrowSync20Regular />} disabled={busy}
            disabledFocusable={!busy && !online} onClick={updatePrices}>
            {busy ? t("Updating…") : t("Update prices")}</Button>
        </Tooltip>
        <Button appearance="primary" icon={<Add20Regular />} disabled={!invAccounts.length}
          onClick={() => setEdit("new")}>{t("Add holding")}</Button>
      </PageHead>
      {refs.data && !invAccounts.length && (
        <Banner kind="info" action={<Link href="/accounts/"><Button size="small">{t("Accounts")}</Button></Link>}>
          {t("Create an account of type “Investment” first.")}</Banner>)}
      {msg && <Banner kind={msg.kind} onClose={() => setMsg(null)}>{msg.text}</Banner>}
      {holdings.error && <Banner kind="error">{holdings.error}</Banner>}
      {holdings.loading && !holdings.data && <Spinner />}
      <div className="kpis">
        <Kpi label={t("Market value")} value={money(value, base)}
          sub={t("Cost basis {v}", { v: money(cost, undefined, 0) })} />
        <Kpi label={t("Unrealised gain")} value={money(value - cost, base)} cls={signClass(value - cost)}
          sub={cost ? pct((value - cost) / cost) : undefined} />
        <Kpi label={t("Money-weighted return (XIRR)")} value={pct(p?.total.xirr)}
          cls={signClass(p?.total.xirr)} sub={t("per year, includes your timing")} />
        <Kpi label={t("Time-weighted return")} value={pct(p?.total.twr_cumulative)}
          cls={signClass(p?.total.twr_cumulative)}
          sub={p?.total.twr_annualised != null
            ? t("{v} per year", { v: pct(p.total.twr_annualised) }) : t("since first trade")} />
        <Kpi label={t("Dividends (12 months)")} value={money(p?.total.dividends_12m ?? 0, base)}
          sub={t("Realised {v}", { v: money(sum("realized_pl"), undefined, 0) })} />
      </div>
      <TabList selectedValue={tab} onTabSelect={(_, d) => setTab(String(d.value))}
        style={{ marginBottom: 12 }}>
        <Tab value="holdings">{t("Holdings")}</Tab>
        <Tab value="performance">{t("Performance")}</Tab>
        <Tab value="income">{t("Income")}</Tab>
        <Tab value="allocation">{t("Allocation")}</Tab>
      </TabList>

      {tab === "holdings" && (
        <div className="card table-wrap" style={{ padding: "4px 8px" }}>
          {hs.length === 0 ? <Empty>{t("No holdings yet.")}</Empty> : (
            <table>
              <thead><tr><th>{t("Holding")}</th><th className="num">{t("Quantity")}</th>
                <th className="num">{t("Avg cost")}</th><th className="num">{t("Price")}</th>
                <th className="num">{t("Value")}</th><th className="num">{t("Gain")}</th>
                <th className="num">XIRR</th><th /></tr></thead>
              <tbody>{hs.map((h) => (
                <tr key={h.id}>
                  <td><div className="row">
                    <b>{h.symbol}</b>
                    <Badge appearance="tint">{t(ASSET_CLASSES[h.asset_class])}</Badge>
                    {h.price_source !== "manual" && <Badge appearance="tint" color="brand">{h.price_source}</Badge>}
                  </div><span className="cell-sub">{h.name}</span></td>
                  <td className="num">{num(h.quantity, 4)}</td>
                  <td className="num">{money(h.avg_cost, h.currency)}</td>
                  <td className="num">{money(h.last_price, h.currency)}
                    <span className="cell-sub">{date(h.price_date)}</span></td>
                  <td className="num">{money(h.market_value, h.currency)}</td>
                  <td className={`num ${signClass(h.unrealized_pl)}`}>{money(h.unrealized_pl)}
                    <span className="cell-sub">{pct(h.unrealized_pl_pct)}</span></td>
                  <td className={`num ${signClass(xirrOf(h.id))}`}>{pct(xirrOf(h.id))}</td>
                  <td className="actions">
                    <Button size="small" onClick={() => setTrade(h)}>{t("Trade")}</Button>{" "}
                    <Menu>
                      <MenuTrigger disableButtonEnhancement>
                        <Button appearance="subtle" size="small" icon={<MoreHorizontal20Regular />}
                          aria-label={t("More")} /></MenuTrigger>
                      <MenuPopover><MenuList>
                        <MenuItem onClick={() => setPrice(h)}>{t("Enter price")}</MenuItem>
                        <MenuItem disabled={h.price_source === "manual"} onClick={async () => {
                          try {
                            const r = await post<{ new_prices: number }>(`/api/holdings/${h.id}/prices/update`);
                            setMsg({ kind: "success", text: t("{n} new prices for {s}.", { n: r.new_prices, s: h.symbol }) });
                            reload();
                          } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
                        }}>{t("Download prices")}</MenuItem>
                        <MenuItem onClick={() => setHistory(h)}>{t("Trade history")}</MenuItem>
                        <MenuDivider />
                        <MenuItem onClick={() => setEdit(h)}>{t("Edit")}</MenuItem>
                        <MenuItem onClick={() => setRemove(h)}>{t("Delete")}</MenuItem>
                      </MenuList></MenuPopover>
                    </Menu>
                  </td>
                </tr>))}</tbody>
            </table>)}
        </div>)}

      {tab === "performance" && (
        <Section title={t("Monthly time-weighted return")}
          sub={t("Modified Dietz per month, chained. Removes the effect of when you added or withdrew money, so it can be compared with an index.")}>
          {twrFig ? <Plot figure={twrFig} height={320} /> : <Empty>{t("No trades yet.")}</Empty>}
          <p className="caption">{t("Between price dates the last known price is used, so sparse prices smooth the monthly returns. Download prices for more accurate figures.")}</p>
        </Section>)}

      {tab === "income" && (
        <div className="grid g2">
          <Section title={t("Dividends per year")}>
            {divFig ? <Plot figure={divFig} height={280} /> : <Empty>{t("No dividends recorded.")}</Empty>}
          </Section>
          <Section title={t("Trailing 12-month yield")}>
            {!p?.holdings.length ? <Empty>{t("No holdings yet.")}</Empty> : (
              <div className="table-wrap"><table>
                <thead><tr><th>{t("Holding")}</th><th className="num">{t("Dividends (12 months)")}</th>
                  <th className="num">{t("Yield")}</th></tr></thead>
                <tbody>{p.holdings.map((r) => (
                  <tr key={r.id}><td>{r.symbol}</td><td className="num">{money(r.dividends_12m, base)}</td>
                    <td className="num">{pct(r.yield_12m, 2)}</td></tr>))}</tbody>
              </table></div>)}
          </Section>
        </div>)}

      {tab === "allocation" && (
        <div className="grid g2">
          <Section title={t("Allocation by asset class")}>
            <Plot figure={alloc.data} height={300} /></Section>
          <Section title={t("Actual vs. target")}
            actions={<Button size="small" icon={<TargetArrow20Regular />} onClick={() => setTargets(true)}>
              {t("Set targets")}</Button>}>
            {!p?.allocation.length ? <Empty>{t("No holdings yet.")}</Empty> : (
              <div className="table-wrap"><table>
                <thead><tr><th>{t("Asset class")}</th><th className="num">{t("Actual")}</th>
                  <th className="num">{t("Target")}</th><th className="num">{t("Drift")}</th>
                  <th className="num">{t("To rebalance")}</th></tr></thead>
                <tbody>{p.allocation.map((a) => (
                  <tr key={a.asset_class}>
                    <td>{t(ASSET_CLASSES[a.asset_class])}</td>
                    <td className="num">{num(a.actual_pct, 1)} %</td>
                    <td className="num">{a.target_pct == null ? "—" : `${num(a.target_pct, 0)} %`}</td>
                    <td className={`num ${a.drift_pp != null && Math.abs(a.drift_pp) > 5 ? "neg" : ""}`}>
                      {a.drift_pp == null ? "—" : `${a.drift_pp > 0 ? "+" : ""}${num(a.drift_pp, 1)} pp`}</td>
                    <td className="num">{a.rebalance == null ? "—"
                      : `${a.rebalance > 0 ? t("buy") : t("sell")} ${money(Math.abs(a.rebalance), base, 0)}`}</td>
                  </tr>))}</tbody>
              </table></div>)}
            <p className="caption">{t("Rebalancing amounts are arithmetic only, before fees and taxes; they are not investment advice.")}</p>
          </Section>
        </div>)}

      {targets && <TargetsDialog current={refs.data?.settings.allocation_targets ?? {}}
        onClose={() => setTargets(false)} onSaved={reload} />}
      {edit && (() => {
        const h = edit === "new" ? null : edit;
        return (
          <FormModal title={h ? t("Edit {name}", { name: h.symbol }) : t("Add holding")}
            onClose={() => setEdit(null)}
            initial={h ? { account_id: h.account_id, symbol: h.symbol, name: h.name,
              asset_class: h.asset_class, currency: h.currency, price_source: h.price_source,
              price_symbol: h.price_symbol ?? "", notes: h.notes ?? "" }
              : { account_id: invAccounts[0]?.value ?? "", symbol: "", name: "", asset_class: "etf",
                currency: base, price_source: "manual", price_symbol: "", notes: "" }}
            fields={(v) => [
              { name: "account_id", label: t("Investment account"), type: "select", required: true, options: invAccounts },
              { name: "symbol", label: t("Symbol / ticker"), required: true },
              { name: "name", label: t("Name"), required: true, full: true },
              { name: "asset_class", label: t("Asset class"), type: "select", required: true,
                options: Object.entries(ASSET_CLASSES).map(([value, label]) => ({ value, label: t(label) })) },
              { name: "currency", label: t("Trading currency"), type: "select", required: true,
                options: CURRENCIES.map((c) => ({ value: c, label: c })) },
              { name: "price_source", label: t("Price source"), type: "select", required: true,
                options: Object.entries(SOURCES).map(([value, label]) => ({ value, label: t(label) })) },
              { name: "price_symbol", label: t("Symbol at the price source"), hidden: v.price_source === "manual",
                placeholder: v.price_source === "coingecko" ? "bitcoin" : "vt.us",
                help: v.price_source === "coingecko"
                  ? t("CoinGecko coin id, e.g. bitcoin or ethereum. Prices are in the trading currency.")
                  : t("stooq symbol with market suffix, e.g. vt.us, vwrl.uk, sap.de. Prices are end of day in the listing currency. Needs your free stooq API key in Settings.") },
              { name: "notes", label: t("Notes"), type: "textarea", full: true },
            ]}
            onSubmit={async (v) => {
              const body = { ...v, account_id: Number(v.account_id),
                price_symbol: v.price_symbol || null, notes: v.notes || null };
              if (h) await put(`/api/holdings/${h.id}`, body); else await post("/api/holdings", body);
              reload();
            }} />);
      })()}
      {trade && (
        <FormModal title={t("Record trade: {s}", { s: trade.symbol })} onClose={() => setTrade(null)}
          initial={{ trade_type: "buy", trade_date: today(), quantity: "", price: trade.last_price ?? "",
            fees: "0", cash_amount: "", affects_cash: true, notes: "" }}
          fields={(v) => {
            const qty = v.trade_type === "buy" || v.trade_type === "sell";
            return [
              { name: "trade_type", label: t("Type"), type: "select", required: true, options: [
                { value: "buy", label: t("Buy") }, { value: "sell", label: t("Sell") },
                { value: "dividend", label: t("Dividend") }, { value: "fee", label: t("Fee") }] },
              { name: "trade_date", label: t("Date"), type: "date", required: true },
              { name: "quantity", label: t("Quantity"), type: "number", step: "any", hidden: !qty, required: qty },
              { name: "price", label: t("Price per unit ({cur})", { cur: trade.currency }), type: "number",
                step: "any", hidden: !qty, required: qty },
              { name: "fees", label: t("Fees"), type: "number", step: "0.01", hidden: !qty },
              { name: "cash_amount", label: t("Amount ({cur})", { cur: trade.currency }), type: "number",
                step: "0.01", hidden: qty, required: !qty },
              { name: "affects_cash", label: t("Book the cash movement on the account"), type: "switch", full: true },
              { name: "notes", label: t("Notes"), full: true },
            ];
          }}
          onSubmit={async (v) => {
            const s = (x: unknown) => (x === "" || x === null ? "0" : String(x));
            await post(`/api/holdings/${trade.id}/trades`, {
              trade_type: v.trade_type, trade_date: v.trade_date, quantity: s(v.quantity),
              price: s(v.price), fees: s(v.fees),
              cash_amount: v.cash_amount === "" ? null : String(v.cash_amount),
              affects_cash: v.affects_cash, notes: v.notes || null });
            reload();
          }} />)}
      {price && (
        <FormModal title={t("Enter price: {s}", { s: price.symbol })} onClose={() => setPrice(null)}
          initial={{ price_date: today(), price: price.last_price ?? "" }}
          fields={[
            { name: "price_date", label: t("Date"), type: "date", required: true },
            { name: "price", label: t("Price ({cur})", { cur: price.currency }), type: "number", step: "any", required: true },
          ]}
          onSubmit={async (v) => {
            await post(`/api/holdings/${price.id}/prices`, { price_date: v.price_date, price: String(v.price) });
            reload();
          }} />)}
      {history && <TradeHistory h={history} onClose={() => setHistory(null)} onChange={reload} />}
      {remove && <Confirm danger yesLabel={t("Delete")} onClose={() => setRemove(null)}
        text={t("Delete {s} with all its trades, prices and the cash transactions they booked?", { s: remove.symbol })}
        onYes={async () => { await del(`/api/holdings/${remove.id}`); reload(); }} />}
    </>
  );
}

function TradeHistory({ h, onClose, onChange }: { h: Holding; onClose: () => void; onChange: () => void }) {
  const t = useT();
  const trades = useLoad(() => get<Trade[]>(`/api/holdings/${h.id}/trades`));
  const [error, setError] = useState<string | null>(null);
  const TYPES: Record<string, string> = { buy: "Buy", sell: "Sell", dividend: "Dividend", fee: "Fee" };
  return (
    <Modal title={t("{s}: trade history", { s: h.symbol })} onClose={onClose} wide
      actions={<Button onClick={onClose}>{t("Close")}</Button>}>
      {error && <Banner kind="error">{error}</Banner>}
      {trades.data?.length === 0 && <Empty>{t("No trades.")}</Empty>}
      {!!trades.data?.length && (
        <div className="table-wrap"><table><thead><tr><th>{t("Date")}</th><th>{t("Type")}</th>
          <th className="num">{t("Quantity")}</th><th className="num">{t("Price")}</th>
          <th className="num">{t("Fees")}</th><th className="num">{t("Cash")}</th><th /></tr></thead>
          <tbody>{trades.data.map((x) => (
            <tr key={x.id}><td>{date(x.trade_date)}</td><td>{t(TYPES[x.trade_type] ?? x.trade_type)}</td>
              <td className="num">{num(x.quantity, 4)}</td><td className="num">{money(x.price)}</td>
              <td className="num">{money(x.fees)}</td><td className="num">{money(x.cash_amount)}</td>
              <td className="actions"><Button appearance="subtle" size="small" onClick={async () => {
                try { await del(`/api/trades/${x.id}`); trades.reload(); onChange(); }
                catch (e) { setError((e as Error).message); }
              }}>{t("Delete")}</Button></td></tr>))}</tbody></table></div>)}
    </Modal>
  );
}
