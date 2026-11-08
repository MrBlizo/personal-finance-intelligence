"use client";
import Link from "next/link";
import { useState } from "react";
import Plot from "@/components/Plot";
import { accountOptions, useRefs } from "@/components/refs";
import {
  Banner, Confirm, Empty, FormModal, Kpi, Modal, PageHead, Spinner, useLoad,
} from "@/components/ui";
import { Holding, PlotFigure, Trade, del, get, post, put } from "@/lib/api";
import { ASSET_CLASSES, CURRENCIES, date, money, num, pct, signClass, today } from "@/lib/format";

export default function Investments() {
  const refs = useRefs();
  const holdings = useLoad(() => get<Holding[]>("/api/holdings"));
  const alloc = useLoad(() => get<PlotFigure>("/api/analytics/charts/allocation"));
  const [edit, setEdit] = useState<Holding | "new" | null>(null);
  const [trade, setTrade] = useState<Holding | null>(null);
  const [price, setPrice] = useState<Holding | null>(null);
  const [history, setHistory] = useState<Holding | null>(null);
  const [remove, setRemove] = useState<Holding | null>(null);
  const reload = () => { holdings.reload(); alloc.reload(); refs.reload(); };
  const base = refs.data?.settings.base_currency ?? "CHF";
  const invAccounts = accountOptions(refs.data?.accounts ?? [], (a) => a.type === "investment");
  const hs = holdings.data ?? [];
  const sum = (k: keyof Holding) => hs.reduce((s, h) => s + ((h[k] as number | null) ?? 0), 0);
  const value = sum("market_value_base");
  const cost = sum("cost_basis_base");

  return (
    <>
      <PageHead title="Investments" sub="Average-cost method; prices are entered manually">
        <button className="primary" disabled={!invAccounts.length} onClick={() => setEdit("new")}>+ Add holding</button>
      </PageHead>
      {refs.data && !invAccounts.length && (
        <Banner kind="info">Create an account of type <b>Investment</b> on the <Link href="/accounts/">Accounts</Link> page first.</Banner>)}
      {holdings.error && <Banner kind="error">{holdings.error}</Banner>}
      {holdings.loading && !holdings.data && <Spinner />}
      <div className="stack">
        <div className="grid kpis">
          <Kpi label="Market value" value={money(value, base)} />
          <Kpi label="Cost basis" value={money(cost, base)} />
          <Kpi label="Unrealized gain" value={money(value - cost, base)} cls={signClass(value - cost)}
            sub={cost ? pct((value - cost) / cost) : undefined} />
          <Kpi label="Dividends (all time)" value={money(sum("dividends"), base)}
            sub={`Realized: ${money(sum("realized_pl"), undefined)}`} />
        </div>
        <div className="card table-wrap">
            {hs.length === 0 ? <Empty>No holdings yet.</Empty> : (
              <table>
                <thead><tr><th>Holding</th><th className="num">Quantity</th><th className="num">Avg cost</th>
                  <th className="num">Price</th><th className="num">Value</th><th className="num">Gain</th><th /></tr></thead>
                <tbody>{hs.map((h) => (
                  <tr key={h.id}>
                    <td><b>{h.symbol}</b> <span className="badge">{ASSET_CLASSES[h.asset_class]}</span>
                      <div className="small muted">{h.name}</div></td>
                    <td className="num">{num(h.quantity, 4)}</td>
                    <td className="num">{money(h.avg_cost, h.currency)}</td>
                    <td className="num">{money(h.last_price, h.currency)}
                      <div className="small muted">{date(h.price_date)}</div></td>
                    <td className="num">{money(h.market_value, h.currency)}</td>
                    <td className={`num ${signClass(h.unrealized_pl)}`}>{money(h.unrealized_pl)}
                      <div className="small">{pct(h.unrealized_pl_pct)}</div></td>
                    <td className="num">
                      <button className="link" onClick={() => setTrade(h)}>Trade</button>
                      <button className="link" onClick={() => setPrice(h)}>Price</button>
                      <button className="link" onClick={() => setHistory(h)}>History</button>
                      <button className="link" onClick={() => setEdit(h)}>Edit</button>
                      <button className="link danger" onClick={() => setRemove(h)}>Delete</button>
                    </td>
                  </tr>))}</tbody>
              </table>)}
        </div>
        <div className="grid g2">
          <div className="card"><h3>Allocation by asset class</h3><Plot figure={alloc.data} height={300} /></div>
        </div>
      </div>

      {edit && (() => {
        const h = edit === "new" ? null : edit;
        return (
          <FormModal title={h ? `Edit ${h.symbol}` : "Add holding"} onClose={() => setEdit(null)}
            initial={h ? { account_id: h.account_id, symbol: h.symbol, name: h.name,
              asset_class: h.asset_class, currency: h.currency, notes: "" }
              : { account_id: invAccounts[0]?.value ?? "", symbol: "", name: "", asset_class: "etf",
                currency: base, notes: "" }}
            fields={[
              { name: "account_id", label: "Investment account", type: "select", required: true, options: invAccounts },
              { name: "symbol", label: "Symbol / ticker", required: true },
              { name: "name", label: "Name", required: true, full: true },
              { name: "asset_class", label: "Asset class", type: "select", required: true,
                options: Object.entries(ASSET_CLASSES).map(([value, label]) => ({ value, label })) },
              { name: "currency", label: "Trading currency", type: "select", required: true,
                options: CURRENCIES.map((c) => ({ value: c, label: c })) },
            ]}
            onSubmit={async (v) => {
              const body = { ...v, account_id: Number(v.account_id), notes: null };
              if (h) await put(`/api/holdings/${h.id}`, body); else await post("/api/holdings", body);
              reload();
            }} />);
      })()}
      {trade && (
        <FormModal title={`Record trade: ${trade.symbol}`} onClose={() => setTrade(null)}
          initial={{ trade_type: "buy", trade_date: today(), quantity: "", price: trade.last_price ?? "",
            fees: "0", cash_amount: "", affects_cash: true, notes: "" }}
          onChange={(v) => v}
          fields={[
            { name: "trade_type", label: "Type", type: "select", required: true, options: [
              { value: "buy", label: "Buy" }, { value: "sell", label: "Sell" },
              { value: "dividend", label: "Dividend" }, { value: "fee", label: "Fee" }] },
            { name: "trade_date", label: "Date", type: "date", required: true },
            { name: "quantity", label: "Quantity (buy/sell)", type: "number", step: "any" },
            { name: "price", label: `Price per unit (${trade.currency})`, type: "number", step: "any" },
            { name: "fees", label: "Fees", type: "number", step: "0.01" },
            { name: "cash_amount", label: "Cash amount (dividend/fee)", type: "number", step: "0.01" },
            { name: "affects_cash", label: "Book the cash movement on the account", type: "checkbox", full: true },
            { name: "notes", label: "Notes", full: true },
          ]}
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
        <FormModal title={`Update price: ${price.symbol}`} onClose={() => setPrice(null)}
          initial={{ price_date: today(), price: price.last_price ?? "" }}
          fields={[
            { name: "price_date", label: "Date", type: "date", required: true },
            { name: "price", label: `Price (${price.currency})`, type: "number", step: "any", required: true },
          ]}
          onSubmit={async (v) => {
            await post(`/api/holdings/${price.id}/prices`, { price_date: v.price_date, price: String(v.price) });
            reload();
          }} />)}
      {history && <TradeHistory h={history} onClose={() => setHistory(null)} onChange={reload} />}
      {remove && <Confirm onClose={() => setRemove(null)}
        text={`Delete ${remove.symbol} with all its trades, prices and the cash transactions they booked?`}
        onYes={async () => { await del(`/api/holdings/${remove.id}`); reload(); }} />}
    </>
  );
}

function TradeHistory({ h, onClose, onChange }: { h: Holding; onClose: () => void; onChange: () => void }) {
  const trades = useLoad(() => get<Trade[]>(`/api/holdings/${h.id}/trades`));
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal title={`${h.symbol} — trade history`} onClose={onClose} wide
      actions={<button onClick={onClose}>Close</button>}>
      {error && <Banner kind="error">{error}</Banner>}
      {trades.data?.length === 0 && <Empty>No trades.</Empty>}
      {!!trades.data?.length && (
        <table><thead><tr><th>Date</th><th>Type</th><th className="num">Qty</th>
          <th className="num">Price</th><th className="num">Fees</th><th className="num">Cash</th><th /></tr></thead>
          <tbody>{trades.data.map((t) => (
            <tr key={t.id}><td>{date(t.trade_date)}</td><td>{t.trade_type}</td>
              <td className="num">{num(t.quantity, 4)}</td><td className="num">{money(t.price)}</td>
              <td className="num">{money(t.fees)}</td><td className="num">{money(t.cash_amount)}</td>
              <td className="num"><button className="link danger" onClick={async () => {
                try { await del(`/api/trades/${t.id}`); trades.reload(); onChange(); }
                catch (e) { setError((e as Error).message); }
              }}>Delete</button></td></tr>))}</tbody></table>)}
    </Modal>
  );
}
