"""Monthly PDF report, Excel workbook and CSV export.

All figures come from the same services as the screens (base currency,
FX at transaction date), so a report always matches what the app shows.
Nothing is estimated: when a currency cannot be converted the affected
rows are left out of totals and listed under "Data notes".
"""
import csv
import io
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..models import Account, Budget, Transaction
from . import performance
from .frame import expenses, incomes, load_transactions
from .fx import FxConverter
from .ledger import account_balances, holding_valuations, net_worth
from .planning import add_months, budget_status, month_bounds

LABELS = {
    "en": {
        "title": "Monthly report", "generated": "Generated",
        "income": "Income", "expenses": "Expenses", "net": "Net savings",
        "rate": "Savings rate", "networth": "Net worth (end of month)",
        "change": "Net worth change vs. previous month",
        "spending": "Spending by category", "category": "Category",
        "this": "This month", "prev": "Previous", "avg3": "3-month avg.",
        "budgets": "Budgets", "budget": "Budget", "spent": "Spent",
        "status": "Status", "largest": "Largest expenses", "date": "Date",
        "description": "Description", "amount": "Amount",
        "merchants": "Top payees", "payee": "Payee", "count": "Count",
        "invest": "Investments", "value": "Portfolio value",
        "month_return": "Return this month (time-weighted)",
        "dividends": "Dividends received", "notes": "Data notes",
        "uncat": "uncategorised expenses totalling",
        "missing_fx": "No exchange rate for", "none": "None.",
        "ok": "on track", "at_risk": "at risk", "over": "over budget",
        "footer": "Personal Finance Intelligence",
    },
    "fr": {
        "title": "Rapport mensuel", "generated": "Généré le",
        "income": "Revenus", "expenses": "Dépenses",
        "net": "Épargne nette", "rate": "Taux d'épargne",
        "networth": "Patrimoine net (fin du mois)",
        "change": "Variation du patrimoine vs. mois précédent",
        "spending": "Dépenses par catégorie", "category": "Catégorie",
        "this": "Ce mois", "prev": "Précédent", "avg3": "Moy. 3 mois",
        "budgets": "Budgets", "budget": "Budget", "spent": "Dépensé",
        "status": "Statut", "largest": "Plus grosses dépenses",
        "date": "Date", "description": "Description", "amount": "Montant",
        "merchants": "Principaux bénéficiaires", "payee": "Bénéficiaire",
        "count": "Nombre", "invest": "Investissements",
        "value": "Valeur du portefeuille",
        "month_return": "Rendement du mois (pondéré dans le temps)",
        "dividends": "Dividendes reçus", "notes": "Remarques sur les données",
        "uncat": "dépenses non catégorisées pour un total de",
        "missing_fx": "Aucun taux de change pour", "none": "Aucune.",
        "ok": "dans les clous", "at_risk": "à risque",
        "over": "dépassé", "footer": "Personal Finance Intelligence",
    },
}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
}


def _by_top(df: pd.DataFrame) -> pd.Series:
    return expenses(df).groupby("top_category")["spend"].sum()


def monthly_data(db: Session, fx: FxConverter, base: str, month: date,
                 today: date | None = None) -> dict:
    """Collect every figure shown in the monthly report.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    month : date
        Any day of the month to report on.
    today : date, optional
        The reference date for budget projections.

    Returns
    -------
    dict
        Totals, category table, budgets, largest expenses, top payees,
        investment figures and data-quality notes.
    """
    first, last = month_bounds(month)
    prev_first = add_months(first, -1)
    df = load_transactions(db, fx, base, first, last)
    hist = load_transactions(db, fx, base, add_months(first, -3),
                             first - timedelta(days=1))
    exp, inc = expenses(df), incomes(df)
    income, spend = float(inc["amount_base"].sum()), float(exp["spend"].sum())
    this = _by_top(df)
    prev = _by_top(hist[hist["txn_date"] >= pd.Timestamp(prev_first)])
    avg3 = _by_top(hist) / 3
    cats = sorted(set(this.index) | set(prev.index),
                  key=lambda c: -float(this.get(c, 0)))
    nw_end = net_worth(db, fx, base, last)
    nw_prev = net_worth(db, fx, base, first - timedelta(days=1))
    largest = exp.sort_values("spend", ascending=False).head(10)
    payee = exp.assign(payee=exp["merchant"].fillna(exp["description"])
                       .str.slice(0, 40))
    top_payees = (payee.groupby("payee")["spend"].agg(["sum", "count"])
                  .sort_values("sum", ascending=False).head(8))
    uncat = exp[exp["category_id"].isna()]
    twr = performance.time_weighted(db, fx, base, today=last)
    month_ret = next((m["return"] for m in twr["months"]
                      if m["month"] == first.strftime("%Y-%m")), None)
    div = sum(v for d, v, k, _ in performance._flows(db, fx, base)
              if k == "dividend" and first <= d <= last)
    port = sum(h["market_value_base"] or 0
               for h in holding_valuations(db, fx, base, last))
    return {
        "month": first, "currency": base, "income": income,
        "expenses": spend, "net": income - spend,
        "savings_rate": (income - spend) / income if income > 0 else None,
        "net_worth": nw_end.total,
        "net_worth_change": nw_end.total - nw_prev.total,
        "categories": [{"category": c, "this": float(this.get(c, 0)),
                        "prev": float(prev.get(c, 0)),
                        "avg3": float(avg3.get(c, 0))} for c in cats],
        "budgets": budget_status(db, fx, base, first, today)["items"],
        "largest": [{"date": r.txn_date.date(), "description":
                     (r.merchant or r.description)[:60],
                     "category": r.category, "amount": r.spend}
                    for r in largest.itertuples()],
        "payees": [{"payee": k, "amount": float(v["sum"]),
                    "count": int(v["count"])}
                   for k, v in top_payees.iterrows()],
        "portfolio_value": port, "month_return": month_ret,
        "dividends": div,
        "uncategorised": {"count": int(len(uncat)),
                          "amount": float(uncat["spend"].sum())},
        "missing_fx": sorted(set(df.attrs["missing_fx"])
                             | nw_end.missing_fx),
    }


def _money(v: float | None, cur: str = "") -> str:
    if v is None:
        return "–"
    s = f"{abs(v):,.2f}".replace(",", "'")
    return f"{'−' if v < 0 else ''}{s}{' ' + cur if cur else ''}"


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:.1f} %"


def render_pdf(data: dict, lang: str = "en") -> bytes:
    """Render the monthly report as an A4 PDF.

    Parameters
    ----------
    data : dict
        The figures from :func:`monthly_data`.
    lang : str
        The report language, ``en`` or ``fr`` (others fall back to ``en``).

    Returns
    -------
    bytes
        The PDF document.
    """
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
        TableStyle)

    L = LABELS.get(lang, LABELS["en"])
    months = MONTHS.get(lang, MONTHS["en"])
    cur = data["currency"]
    accent = colors.HexColor("#005FB8")
    ink, muted = colors.HexColor("#1B1B1B"), colors.HexColor("#616161")
    line = colors.HexColor("#E0E0E0")
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=20,
                        leading=24, textColor=ink)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12,
                        leading=16, textColor=ink, spaceBefore=10,
                        spaceAfter=4)
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=8,
                           leading=10, textColor=muted)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9,
                          leading=12, textColor=ink)

    def table(rows, widths, num_cols=()):
        t = Table(rows, colWidths=widths, repeatRows=1)
        style = [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), muted),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, ink),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, line),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        for c in num_cols:
            style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
        t.setStyle(TableStyle(style))
        return t

    m = data["month"]
    story = [
        Paragraph(f"{L['title']} — {months[m.month - 1]} {m.year}", h1),
        Paragraph(f"{L['generated']} {datetime.now():%Y-%m-%d %H:%M} · "
                  f"{cur} · PFI {__version__}", small),
        Spacer(1, 6 * mm)]
    kpis = [(L["income"], _money(data["income"], cur)),
            (L["expenses"], _money(data["expenses"], cur)),
            (L["net"], _money(data["net"], cur)),
            (L["rate"], _pct(data["savings_rate"])),
            (L["networth"], _money(data["net_worth"], cur))]
    k = Table([[x for x, _ in kpis], [y for _, y in kpis]],
              colWidths=[34 * mm] * 5)
    k.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica", 7.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), muted),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 11),
        ("LINEABOVE", (0, 0), (-1, 0), 2, accent),
        ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    delta = data["net_worth_change"]
    story += [k, Spacer(1, 1.5 * mm), Paragraph(
        f"{L['change']}: {'+' if delta > 0 else ''}{_money(delta, cur)}",
        small)]

    cats = [c for c in data["categories"] if c["this"] or c["prev"]][:12]
    story.append(Paragraph(L["spending"], h2))
    if cats:
        d = Drawing(170 * mm, max(len(cats), 1) * 6 * mm + 6 * mm)
        bc = HorizontalBarChart()
        bc.x, bc.y = 40 * mm, 3 * mm
        bc.width, bc.height = 125 * mm, len(cats) * 6 * mm
        bc.data = [[max(c["this"], 0) for c in reversed(cats)]]
        bc.categoryAxis.categoryNames = [c["category"][:22]
                                         for c in reversed(cats)]
        bc.categoryAxis.labels.fontName = "Helvetica"
        bc.categoryAxis.labels.fontSize = 7.5
        bc.valueAxis.labels.fontSize = 7
        bc.valueAxis.labels.fontName = "Helvetica"
        bc.valueAxis.valueMin = 0
        bc.bars[0].fillColor = accent
        bc.bars[0].strokeColor = None
        d.add(bc)
        story.append(d)
        story.append(table(
            [[L["category"], L["this"], L["prev"], L["avg3"]]]
            + [[c["category"], _money(c["this"]), _money(c["prev"]),
                _money(c["avg3"])] for c in cats],
            [70 * mm, 33 * mm, 33 * mm, 33 * mm], (1, 2, 3)))
    else:
        story.append(Paragraph(L["none"], body))

    if data["budgets"]:
        story.append(KeepTogether([
            Paragraph(L["budgets"], h2),
            table([[L["category"], L["budget"], L["spent"], "%",
                    L["status"]]]
                  + [[b["category"], _money(b["budget"]),
                      _money(b["spent"]), _pct(b["pct"]),
                      L.get(b["status"], b["status"])]
                     for b in data["budgets"]],
                  [60 * mm, 30 * mm, 30 * mm, 20 * mm, 30 * mm],
                  (1, 2, 3))]))
    story.append(Paragraph(L["largest"], h2))
    story.append(table(
        [[L["date"], L["description"], L["category"], L["amount"]]]
        + [[str(r["date"]), r["description"], r["category"],
            _money(r["amount"])] for r in data["largest"]]
        if data["largest"] else [[L["none"]]],
        [22 * mm, 80 * mm, 40 * mm, 28 * mm] if data["largest"]
        else [170 * mm], (3,) if data["largest"] else ()))
    if data["payees"]:
        story.append(KeepTogether([
            Paragraph(L["merchants"], h2),
            table([[L["payee"], L["count"], L["amount"]]]
                  + [[p["payee"], str(p["count"]), _money(p["amount"])]
                     for p in data["payees"]],
                  [110 * mm, 25 * mm, 35 * mm], (1, 2))]))
    if data["portfolio_value"]:
        story.append(KeepTogether([
            Paragraph(L["invest"], h2),
            table([["", ""],
                   [L["value"], _money(data["portfolio_value"], cur)],
                   [L["month_return"], _pct(data["month_return"])],
                   [L["dividends"], _money(data["dividends"], cur)]],
                  [110 * mm, 60 * mm], (1,))]))
    notes = []
    if data["uncategorised"]["count"]:
        notes.append(f"{data['uncategorised']['count']} {L['uncat']} "
                     f"{_money(data['uncategorised']['amount'], cur)}.")
    if data["missing_fx"]:
        notes.append(f"{L['missing_fx']}: {', '.join(data['missing_fx'])}.")
    story.append(Paragraph(L["notes"], h2))
    story.append(Paragraph(" ".join(notes) or L["none"], body))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 10 * mm, L["footer"])
        canvas.drawRightString(192 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm,
                      rightMargin=18 * mm, topMargin=16 * mm,
                      bottomMargin=16 * mm,
                      title=f"{L['title']} {m:%Y-%m}",
                      author="Personal Finance Intelligence").build(
        story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


EXPORT_COLUMNS = ["date", "account", "account_currency", "amount", "kind",
                  "category", "description", "merchant", "notes",
                  "amount_base", "base_currency"]


def transaction_rows(db: Session, fx: FxConverter, base: str,
                     start: date | None = None, end: date | None = None,
                     account_id: int | None = None) -> list[list]:
    """Return transactions as export rows (oldest first)."""
    from .frame import load_transactions as _load
    df = _load(db, fx, base, start, end, include_transfers=True)
    if account_id:
        df = df[df["account_id"] == account_id]
    notes = dict(db.execute(select(Transaction.id, Transaction.notes)
                            .where(Transaction.notes.is_not(None))).all())
    rows = []
    for r in df.itertuples():
        rows.append([r.txn_date.date(), r.account_name, r.currency,
                     round(r.amount, 2), r.kind, r.category,
                     r.description, r.merchant or "", notes.get(r.id, ""),
                     None if pd.isna(r.amount_base)
                     else round(r.amount_base, 2), base])
    return rows


def to_csv(rows: list[list]) -> bytes:
    """Serialise export rows as UTF-8 CSV with a BOM (opens in Excel)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(EXPORT_COLUMNS)
    w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def workbook(db: Session, fx: FxConverter, base: str,
             today: date | None = None) -> bytes:
    """Build an Excel workbook with all data and monthly summaries.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    today : date, optional
        The reference date; defaults to today.

    Returns
    -------
    bytes
        The ``.xlsx`` file content.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    today = today or date.today()
    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="005FB8")
    money_fmt = '#,##0.00;[Red]-#,##0.00'

    def sheet(title, header, rows, money_cols=(), widths=None):
        ws = wb.create_sheet(title)
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(vertical="center")
        for r in rows:
            ws.append(r)
        for col in money_cols:
            for cell in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                cell[0].number_format = money_fmt
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = ws.dimensions
        for i, h in enumerate(header, 1):
            ws.column_dimensions[get_column_letter(i)].width = (
                widths[i - 1] if widths else max(12, len(str(h)) + 4))
        return ws

    wb.remove(wb.active)
    df = load_transactions(db, fx, base)
    exp, inc = expenses(df), incomes(df)
    months = sorted(set(df["txn_date"].dt.strftime("%Y-%m")))
    by_m_inc = inc.groupby(inc["txn_date"].dt.strftime("%Y-%m"))[
        "amount_base"].sum()
    by_m_exp = exp.groupby(exp["txn_date"].dt.strftime("%Y-%m"))[
        "spend"].sum()
    summary = []
    for mth in months:
        i, e = float(by_m_inc.get(mth, 0)), float(by_m_exp.get(mth, 0))
        summary.append([mth, i, e, i - e, (i - e) / i if i > 0 else None])
    header = ["Month", "Income", "Expenses", "Net", "Savings rate"]
    ws = sheet(f"Monthly ({base})", header, summary, (2, 3, 4),
               [10, 14, 14, 14, 13])
    for cell in ws.iter_rows(min_row=2, min_col=5, max_col=5):
        cell[0].number_format = "0.0%"
    pivot = (exp.assign(m=exp["txn_date"].dt.strftime("%Y-%m"))
             .pivot_table(index="top_category", columns="m", values="spend",
                          aggfunc="sum", fill_value=0.0))
    sheet(f"Categories ({base})", ["Category"] + list(pivot.columns),
          [[idx] + [float(v) for v in row]
           for idx, row in pivot.iterrows()],
          range(2, len(pivot.columns) + 2),
          [26] + [11] * len(pivot.columns))
    sheet("Transactions", EXPORT_COLUMNS,
          transaction_rows(db, fx, base), (4, 10),
          [11, 22, 9, 12, 9, 22, 40, 22, 24, 13, 8])
    bal = account_balances(db)
    nw = net_worth(db, fx, base)
    by_acc = {a["id"]: a for a in nw.by_account}
    sheet("Accounts", ["Account", "Type", "Currency", "Institution",
                       "Balance", f"Total ({base})", "Archived"],
          [[a.name, a.type, a.currency, a.institution or "",
            float(bal.get(a.id, 0)), by_acc.get(a.id, {}).get("total_base"),
            "yes" if a.is_archived else ""]
           for a in db.scalars(select(Account).order_by(Account.name))],
          (5, 6), [24, 12, 9, 20, 14, 14, 9])
    vals = holding_valuations(db, fx, base, today)
    sheet("Holdings", ["Symbol", "Name", "Class", "Currency", "Quantity",
                       "Avg cost", "Last price", "Price date",
                       "Market value", f"Value ({base})", "Unrealised P/L",
                       "Dividends"],
          [[h["symbol"], h["name"], h["asset_class"], h["currency"],
            h["quantity"], h["avg_cost"], h["last_price"], h["price_date"],
            h["market_value"], h["market_value_base"], h["unrealized_pl"],
            h["dividends"]] for h in vals],
          (6, 7, 9, 10, 11, 12), [10, 28, 10, 9, 11, 11, 11, 11, 13, 13,
                                  13, 11])
    status = budget_status(db, fx, base, today, today)
    sheet(f"Budgets {status['month']}", ["Category", "Budget", "Spent",
                                         "Remaining", "Status"],
          [[b["category"], b["budget"], b["spent"], b["remaining"],
            b["status"]] for b in status["items"]], (2, 3, 4),
          [24, 13, 13, 13, 10])
    info = wb.create_sheet("About")
    info.append(["Exported from Personal Finance Intelligence",
                 __version__])
    info.append(["Exported at", datetime.now().strftime("%Y-%m-%d %H:%M")])
    info.append(["Base currency", base])
    info.append(["Note", "Base-currency amounts use the exchange rate of "
                 "each transaction date. Blank = no rate available."])
    info.column_dimensions["A"].width = 44
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def transaction_count(db: Session) -> int:
    """Number of stored transactions (used for export file names)."""
    return db.scalar(select(func.count(Transaction.id))) or 0


def budget_count(db: Session) -> int:
    """Number of budgets."""
    return db.scalar(select(func.count(Budget.id))) or 0
