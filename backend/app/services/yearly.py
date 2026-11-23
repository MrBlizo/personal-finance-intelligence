"""Year-end report (PDF) and tax export (CSV).

Tax groups are the user's own labels on categories ("Donations", "Medical"
...), stored as a setting on this PC; PFI does not know any country's tax
rules and does not give tax advice. The export simply collects the year's
transactions of the tagged categories for an accountant.
"""
import csv
import io
import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__
from ..models import Category
from . import prefs
from .frame import expenses, incomes, load_transactions
from .fx import FxConverter
from .ledger import net_worth
from .monthly import months_timeline
from .reports import _money, _pct

TAX_GROUPS = ("donations", "medical", "education", "childcare", "business",
              "home_office", "retirement", "taxes_paid", "interest_paid",
              "other")
GROUP_LABEL = {
    "donations": "Donations", "medical": "Medical", "education": "Education",
    "childcare": "Childcare", "business": "Business expenses",
    "home_office": "Home office", "retirement": "Retirement savings",
    "taxes_paid": "Taxes paid", "interest_paid": "Interest paid",
    "other": "Other deductible",
}


def get_tax_groups(db: Session) -> dict[int, str]:
    """Return category id -> tax group, as set by the user."""
    try:
        raw = json.loads(prefs.get(db, "tax_groups") or "{}")
    except json.JSONDecodeError:
        return {}
    return {int(k): v for k, v in raw.items() if v in TAX_GROUPS}


def set_tax_groups(db: Session, groups: dict[int, str | None]) -> None:
    """Store the tax groups (``None`` removes a category's group).

    Parameters
    ----------
    db : Session
        The open database session.
    groups : dict
        The category id mapped to a group from ``TAX_GROUPS`` or None.

    Raises
    ------
    ValueError
        If a group or category is unknown.
    """
    known = set(db.scalars(select(Category.id)))
    current = get_tax_groups(db)
    for cat, group in groups.items():
        if cat not in known:
            raise ValueError(
                f"Category {cat} doesn't exist (it may have been deleted). "
                "Reload the page and try again.")
        if group is None:
            current.pop(cat, None)
        elif group not in TAX_GROUPS:
            raise ValueError(
                f"'{group}' is not a tax group. Use one of: "
                + ", ".join(TAX_GROUPS) + ".")
        else:
            current[cat] = group
    prefs.put(db, "tax_groups", json.dumps(
        {str(k): v for k, v in sorted(current.items())}))
    db.commit()


def _group_of(cat_id, cats: dict, groups: dict) -> str | None:
    """A category's group, inherited from its parent when it has none."""
    while cat_id is not None:
        if cat_id in groups:
            return groups[cat_id]
        cat = cats.get(cat_id)
        cat_id = cat.parent_id if cat else None
    return None


def year_data(db: Session, fx: FxConverter, base: str, year: int) -> dict:
    """Collect the figures of the year-end report.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    year : int
        The calendar year.

    Returns
    -------
    dict
        Year totals, the twelve months, spending per category, top payees,
        net worth at the start and end, and the tax group totals.
    """
    start, end = date(year, 1, 1), date(year, 12, 31)
    df = load_transactions(db, fx, base, start, end)
    exp, inc = expenses(df), incomes(df)
    income, spend = float(inc["amount_base"].sum()), float(exp["spend"].sum())
    last = min(end, date.today())
    months = [m for m in months_timeline(db, fx, base, 12, end)["months"]
              if m["month"].startswith(str(year))]
    cats = (exp.groupby("top_category")["spend"].sum()
            .sort_values(ascending=False))
    payee = exp.assign(payee=exp["merchant"].fillna(exp["description"])
                       .str.slice(0, 40))
    payees = (payee.groupby("payee")["spend"].sum()
              .sort_values(ascending=False).head(10))
    nw_start = net_worth(db, fx, base, date(year - 1, 12, 31))
    nw_end = net_worth(db, fx, base, last)
    groups = get_tax_groups(db)
    all_cats = {c.id: c for c in db.scalars(select(Category))}
    tax: dict[str, float] = {}
    for r in df.itertuples():
        g = _group_of(r.category_id, all_cats, groups)
        if g and r.amount_base == r.amount_base:  # not NaN
            tax[g] = tax.get(g, 0.0) + abs(float(r.amount_base))
    return {
        "year": year, "currency": base, "income": income, "expenses": spend,
        "net": income - spend,
        "savings_rate": (income - spend) / income if income > 0 else None,
        "months": months,
        "categories": [{"category": str(k), "amount": float(v),
                        "share": float(v) / spend if spend else 0.0}
                       for k, v in cats.items() if v > 0.005],
        "payees": [{"payee": str(k), "amount": float(v)}
                   for k, v in payees.items()],
        "net_worth_start": nw_start.total, "net_worth_end": nw_end.total,
        "tax_groups": [{"group": g, "label": GROUP_LABEL[g], "amount": v}
                       for g, v in sorted(tax.items(),
                                          key=lambda x: -x[1])],
        "missing_fx": sorted(set(df.attrs["missing_fx"])
                             | nw_end.missing_fx),
    }


def tax_csv(db: Session, fx: FxConverter, base: str, year: int) -> bytes:
    """The year's transactions in tax-tagged categories, as CSV.

    Parameters
    ----------
    db : Session
        The open database session.
    fx : FxConverter
        The converter used for base-currency amounts.
    base : str
        The reporting currency.
    year : int
        The calendar year.

    Returns
    -------
    bytes
        UTF-8 CSV with one row per transaction (or split part).
    """
    df = load_transactions(db, fx, base, date(year, 1, 1),
                           date(year, 12, 31))
    groups = get_tax_groups(db)
    cats = {c.id: c for c in db.scalars(select(Category))}
    rows = [["tax_group", "date", "category", "description", "account",
             "amount", "currency", "amount_base", "base_currency"]]
    for r in df.itertuples():
        g = _group_of(r.category_id, cats, groups)
        if not g:
            continue
        rows.append([GROUP_LABEL[g], r.txn_date.date().isoformat(),
                     r.category, r.merchant or r.description,
                     r.account_name, f"{r.amount:.2f}", r.currency,
                     "" if r.amount_base != r.amount_base
                     else f"{r.amount_base:.2f}", base])
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


LABELS = {
    "en": {"title": "Year in review", "income": "Income",
           "expenses": "Spending", "net": "Saved", "rate": "Savings rate",
           "nw": "Net worth", "start": "1 January", "end": "End of year",
           "months": "Month by month", "month": "Month", "paid": "Paid",
           "cats": "Where the money went", "category": "Category",
           "amount": "Amount", "share": "Share", "payees": "Top payees",
           "payee": "Payee", "tax": "Tax groups", "group": "Group",
           "tax_note": "Totals of the categories you tagged. Personal "
                       "Finance does not know tax rules; check with your tax "
                       "office or accountant.",
           "none": "None.", "generated": "Generated"},
    "fr": {"title": "Bilan de l'année", "income": "Revenus",
           "expenses": "Dépenses", "net": "Épargné",
           "rate": "Taux d'épargne", "nw": "Patrimoine net",
           "start": "1er janvier", "end": "Fin d'année",
           "months": "Mois par mois", "month": "Mois", "paid": "Payé",
           "cats": "Où est passé l'argent", "category": "Catégorie",
           "amount": "Montant", "share": "Part",
           "payees": "Principaux bénéficiaires", "payee": "Bénéficiaire",
           "tax": "Groupes fiscaux", "group": "Groupe",
           "tax_note": "Totaux des catégories que vous avez marquées. "
                       "Personal Finance ne connaît pas les règles fiscales ; "
                       "vérifiez auprès de votre administration ou comptable.",
           "none": "Aucun.", "generated": "Généré le"},
}


def render_year_pdf(data: dict, lang: str = "en") -> bytes:
    """Render the year-end report as an A4 PDF.

    Parameters
    ----------
    data : dict
        The figures from :func:`year_data`.
    lang : str
        The report language, ``en`` or ``fr`` (others fall back to ``en``).

    Returns
    -------
    bytes
        The PDF document.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

    L = LABELS.get(lang, LABELS["en"])
    cur = data["currency"]
    violet = colors.HexColor("#1A41FF")
    lime = colors.HexColor("#C5F331")
    ink, muted = colors.HexColor("#1D1A24"), colors.HexColor("#625B71")
    line = colors.HexColor("#E7E0EC")
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=26,
                        leading=30, textColor=violet)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12,
                        leading=16, textColor=ink, spaceBefore=12,
                        spaceAfter=4)
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=8,
                           leading=10, textColor=muted)

    def table(rows, widths, num_cols=()):
        t = Table(rows, colWidths=widths, repeatRows=1)
        style = [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                 ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
                 ("TEXTCOLOR", (0, 0), (-1, 0), muted),
                 ("LINEBELOW", (0, 0), (-1, 0), 0.6, ink),
                 ("LINEBELOW", (0, 1), (-1, -1), 0.3, line),
                 ("TOPPADDING", (0, 0), (-1, -1), 3),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        style += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in num_cols]
        t.setStyle(TableStyle(style))
        return t

    story = [Paragraph(f"{L['title']} {data['year']}", h1),
             Paragraph(f"{L['generated']} {datetime.now():%Y-%m-%d} · {cur} · "
                       "Personal Finance "
                       f"{__version__}", small), Spacer(1, 6 * mm)]
    kpis = [(L["income"], _money(data["income"], cur)),
            (L["expenses"], _money(data["expenses"], cur)),
            (L["net"], _money(data["net"], cur)),
            (L["rate"], _pct(data["savings_rate"]))]
    k = Table([[a for a, _ in kpis], [b for _, b in kpis]],
              colWidths=[43 * mm] * 4)
    k.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), lime),
        ("FONT", (0, 0), (-1, 0), "Helvetica", 8),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 13),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    story += [k, Spacer(1, 2 * mm), Paragraph(
        f"{L['nw']}: {L['start']} {_money(data['net_worth_start'], cur)} → "
        f"{L['end']} {_money(data['net_worth_end'], cur)}", small)]
    story.append(Paragraph(L["months"], h2))
    story.append(table(
        [[L["month"], L["income"], L["expenses"], L["paid"], L["net"]]]
        + [[m["month"], _money(m["income"]), _money(m["spent"]),
            _money(m["paid"]), _money(m["net"])] for m in data["months"]]
        if data["months"] else [[L["none"]]],
        [30 * mm, 35 * mm, 35 * mm, 35 * mm, 35 * mm]
        if data["months"] else [170 * mm], (1, 2, 3, 4)))
    story.append(Paragraph(L["cats"], h2))
    story.append(table(
        [[L["category"], L["amount"], L["share"]]]
        + [[c["category"], _money(c["amount"]), _pct(c["share"])]
           for c in data["categories"]]
        if data["categories"] else [[L["none"]]],
        [100 * mm, 40 * mm, 30 * mm] if data["categories"]
        else [170 * mm], (1, 2)))
    if data["payees"]:
        story.append(Paragraph(L["payees"], h2))
        story.append(table([[L["payee"], L["amount"]]]
                           + [[p["payee"], _money(p["amount"])]
                              for p in data["payees"]],
                           [130 * mm, 40 * mm], (1,)))
    story.append(Paragraph(L["tax"], h2))
    story.append(table(
        [[L["group"], L["amount"]]]
        + [[g["label"], _money(g["amount"])] for g in data["tax_groups"]]
        if data["tax_groups"] else [[L["none"]]],
        [130 * mm, 40 * mm] if data["tax_groups"] else [170 * mm], (1,)))
    story.append(Paragraph(L["tax_note"], small))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm,
                      rightMargin=18 * mm, topMargin=16 * mm,
                      bottomMargin=16 * mm,
                      title=f"{L['title']} {data['year']}",
                      author="Personal Finance").build(story)
    return buf.getvalue()
