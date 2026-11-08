"""Downloadable reports: monthly PDF, Excel workbook, CSV, net-worth history."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import prefs, reports
from ..services.fx import FxConverter
from ..services.ledger import base_currency
from .analytics import _net_worth_points

router = APIRouter(prefix="/api")


def _month(value: str | None) -> date:
    if not value:
        today = date.today()
        return today.replace(day=1)
    try:
        return date.fromisoformat(value + "-01" if len(value) == 7
                                  else value).replace(day=1)
    except ValueError as exc:
        raise HTTPException(
            422, f"'{value}' is not a month. Use the format YYYY-MM, e.g. "
            "2026-10.") from exc


def _download(content: bytes, media: str, name: str) -> Response:
    return Response(content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/reports/monthly")
def monthly_json(month: str | None = None, db: Session = Depends(get_db)):
    """The figures of the monthly report as JSON (for the preview)."""
    return reports.monthly_data(db, FxConverter.from_db(db),
                                base_currency(db), _month(month))


@router.get("/reports/monthly.pdf")
def monthly_pdf(month: str | None = None,
                lang: str | None = Query(None, pattern="^(en|fr|ar)$"),
                db: Session = Depends(get_db)):
    """The monthly report as a PDF download."""
    m = _month(month)
    data = reports.monthly_data(db, FxConverter.from_db(db),
                                base_currency(db), m)
    pdf = reports.render_pdf(data, lang or prefs.get(db, "language"))
    return _download(pdf, "application/pdf", f"PFI-report-{m:%Y-%m}.pdf")


@router.get("/export/transactions.csv")
def export_csv(start: date | None = None, end: date | None = None,
               account_id: int | None = None,
               db: Session = Depends(get_db)):
    """All (or filtered) transactions as CSV, oldest first."""
    rows = reports.transaction_rows(db, FxConverter.from_db(db),
                                    base_currency(db), start, end,
                                    account_id)
    return _download(reports.to_csv(rows), "text/csv; charset=utf-8",
                     f"PFI-transactions-{date.today():%Y%m%d}.csv")


@router.get("/export/workbook.xlsx")
def export_xlsx(db: Session = Depends(get_db)):
    """Everything in one Excel workbook with monthly summaries."""
    content = reports.workbook(db, FxConverter.from_db(db),
                               base_currency(db))
    return _download(
        content, "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet", f"PFI-export-{date.today():%Y%m%d}.xlsx")


@router.get("/reports/net-worth")
def net_worth_history(months: int = Query(24, ge=2, le=120),
                      db: Session = Depends(get_db)):
    """Month-end net worth for the last ``months`` months."""
    fx, base = FxConverter.from_db(db), base_currency(db)
    points = _net_worth_points(db, fx, base, date.today(), months)
    for prev, cur in zip(points, points[1:]):
        cur["change"] = cur["total"] - prev["total"]
    return {"currency": base, "points": points}
