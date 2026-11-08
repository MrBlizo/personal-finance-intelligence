"""Synthetic demo dataset so every screen can be explored before real data
is imported. Everything created here is marked ``is_demo`` (accounts) or
``source='demo'`` (rates, prices) and is removed by ``remove_demo``.

The numbers are randomly generated and do not describe anyone's finances.
"""
import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    Account, AssetPrice, Budget, Category, ExchangeRate, Holding,
    InvestmentTrade, RecurringItem, SavingsGoal, Transaction)
from .planning import add_months

CENT = Decimal("0.01")


def _cat(db: Session, name: str, kind: str = "expense") -> int:
    return db.scalar(select(Category.id).where(Category.name == name,
                                               Category.kind == kind))


def seed_demo(db: Session, months: int = 14, seed: int = 7,
              today: date | None = None) -> dict:
    """Create demo accounts, ~14 months of transactions and plans.

    Parameters
    ----------
    db : Session
        The open database session.
    months : int
        The number of months of history to generate.
    seed : int
        The random seed for reproducible demo data.
    today : date, optional
        The last date of generated history (defaults to today).

    Returns
    -------
    dict
        The number of created accounts and transactions.
    """
    if db.scalar(select(Account.id).where(Account.is_demo.is_(True))):
        raise ValueError(
            "Demo data already exists. Remove it first (Settings > Demo "
            "data) before generating it again.")
    rnd = random.Random(seed)
    today = today or date.today()
    start = add_months(today.replace(day=1), -months)
    for d, rate in ((start, "0.94"), (today, "0.93")):
        db.add(ExchangeRate(rate_date=d, from_currency="EUR",
                            to_currency="CHF", rate=Decimal(rate),
                            source="demo"))
    db.add(ExchangeRate(rate_date=start, from_currency="CHF",
                        to_currency="MAD", rate=Decimal("11.2"),
                        source="demo"))
    db.add(ExchangeRate(rate_date=start, from_currency="USD",
                        to_currency="CHF", rate=Decimal("0.80"),
                        source="demo"))
    acc = {
        "pay": Account(name="Demo Salary Account", type="checking",
                       currency="CHF", opening_balance=Decimal("4200"),
                       opening_date=start, is_demo=True,
                       institution="Demo Bank"),
        "save": Account(name="Demo Savings", type="savings",
                        currency="CHF", opening_balance=Decimal("12000"),
                        opening_date=start, is_demo=True),
        "card": Account(name="Demo Credit Card", type="credit_card",
                        currency="CHF", opening_balance=Decimal("0"),
                        opening_date=start, is_demo=True),
        "eur": Account(name="Demo EUR Wallet", type="cash",
                       currency="EUR", opening_balance=Decimal("300"),
                       opening_date=start, is_demo=True),
        "inv": Account(name="Demo Broker", type="investment",
                       currency="CHF", opening_balance=Decimal("5000"),
                       opening_date=start, is_demo=True),
    }
    db.add_all(acc.values())
    db.flush()
    txns: list[Transaction] = []

    def add(a: str, day: date, amount: float, cat: str | None,
            text: str, kind: str = "expense", merchant: str | None = None
            ) -> None:
        txns.append(Transaction(
            account_id=acc[a].id, txn_date=day,
            amount=Decimal(str(amount)).quantize(CENT), kind=kind,
            category_id=_cat(db, cat, "income" if kind == "income"
                             else "expense") if cat else None,
            description=text, merchant=merchant))

    def xfer(a: str, b: str, day: date, amount: float, text: str) -> None:
        group = uuid.uuid4()
        value = Decimal(str(amount)).quantize(CENT)
        for name, signed in ((a, -value), (b, value)):
            txns.append(Transaction(
                account_id=acc[name].id, txn_date=day, amount=signed,
                kind="transfer", description=text, transfer_group=group))

    shops = {"Groceries": ["Migros", "Coop", "Aldi", "Lidl"],
             "Restaurants": ["Pizzeria Roma", "Sushi Bar", "Bistro"],
             "Coffee & Snacks": ["Café Central", "Bakery"],
             "Public Transport": ["SBB", "Bernmobil"],
             "Clothing": ["H&M", "Zalando"],
             "Entertainment": ["Cinema", "Concert Hall"],
             "Pharmacy": ["Pharmacy"]}
    for m in range(months + 1):
        first = add_months(start, m)
        last_day = min(add_months(first, 1) - timedelta(days=1), today)
        if first > today:
            break

        def on(day: int) -> date:
            return min(first.replace(day=min(day, 28)), today)
        add("pay", on(25), 6500 + rnd.choice([0, 0, 0, 1200]), "Salary",
            "Salary University", "income")
        add("pay", on(1), -1850, "Rent", "Rent apartment", merchant="Immo")
        add("pay", on(5), -412.6, "Health Insurance", "Health insurance",
            merchant="Health Insurer")
        add("pay", on(10), -rnd.uniform(70, 140), "Utilities",
            "Electricity & water", merchant="Energie")
        add("card", on(12), -59.9, "Internet & Phone", "Mobile & internet",
            merchant="Telecom")
        add("card", on(3), -15.9, "Subscriptions", "Streaming",
            merchant="StreamFlix")
        xfer("pay", "save", on(26), 800, "Monthly saving")
        day = first
        while day <= last_day:
            for cat, (prob, lo, hi, a) in {
                    "Groceries": (0.45, 15, 120, "card"),
                    "Restaurants": (0.15, 25, 90, "card"),
                    "Coffee & Snacks": (0.4, 3, 12, "pay"),
                    "Public Transport": (0.25, 3, 25, "pay"),
                    "Clothing": (0.03, 40, 180, "card"),
                    "Entertainment": (0.05, 15, 70, "card"),
                    "Pharmacy": (0.03, 8, 45, "pay")}.items():
                if rnd.random() < prob * (1.4 if day.weekday() >= 5
                                          else 1.0):
                    add(a, day, -rnd.uniform(lo, hi), cat,
                        rnd.choice(shops[cat]),
                        merchant=rnd.choice(shops[cat]))
            if rnd.random() < 0.04:
                add("eur", day, -rnd.uniform(10, 60), "Travel",
                    "Trip expenses", merchant="Travel")
            day += timedelta(days=1)
        card_spend = -sum(float(t.amount) for t in txns
                          if t.account_id == acc["card"].id
                          and t.kind != "transfer"
                          and first <= t.txn_date <= last_day)
        if card_spend > 0 and last_day < today:
            xfer("pay", "card", last_day, round(card_spend, 2),
                 "Credit card payment")
    db.add_all(txns)
    holdings = [("VWRL", "Vanguard FTSE All-World ETF", "etf", "CHF",
                 95.0, 30), ("NESN", "Nestlé", "stock", "CHF", 92.0, 15),
                ("CHBOND", "Swiss Bond Fund", "bond", "CHF", 100.0, 10)]
    for sym, name, cls, cur, price, qty in holdings:
        h = Holding(account_id=acc["inv"].id, symbol=sym, name=name,
                    asset_class=cls, currency=cur)
        db.add(h)
        db.flush()
        db.add(InvestmentTrade(holding_id=h.id, trade_date=start,
                               trade_type="buy", quantity=Decimal(qty),
                               price=Decimal(str(price)),
                               fees=Decimal("5")))
        p = price
        for m in range(months + 1):
            d = add_months(start, m)
            if d > today:
                break
            p *= 1 + rnd.gauss(0.005, 0.03)
            db.add(AssetPrice(holding_id=h.id, price_date=d,
                              price=Decimal(str(round(p, 4))),
                              source="demo"))
        cost = Decimal(str(-(qty * price + 5))).quantize(CENT)
        db.add(Transaction(account_id=acc["inv"].id, txn_date=start,
                           amount=cost, kind="transfer",
                           description=f"Buy {qty} {sym} (demo)"))
    for name, amount, cat, freq, a, d in (
            ("Salary", 6500, "Salary", "monthly", "pay", 25),
            ("Rent", -1850, "Rent", "monthly", "pay", 1),
            ("Health insurance", -412.6, "Health Insurance", "monthly",
             "pay", 5),
            ("Mobile & internet", -59.9, "Internet & Phone", "monthly",
             "card", 12),
            ("Streaming", -15.9, "Subscriptions", "monthly", "card", 3)):
        kind = "income" if amount > 0 else "expense"
        db.add(RecurringItem(
            name=f"{name} (demo)", account_id=acc[a].id,
            category_id=_cat(db, cat, kind),
            amount=Decimal(str(amount)), frequency=freq,
            start_date=start.replace(day=d)))
    for cat, amount in (("Food", 900), ("Leisure", 250), ("Transport", 150),
                        ("Shopping", 200)):
        cid = _cat(db, cat)
        if not db.scalar(select(Budget.id).where(Budget.category_id == cid)):
            db.add(Budget(category_id=cid, monthly_amount=Decimal(amount),
                          notes="demo"))
    db.add(SavingsGoal(name="Emergency fund (demo)",
                       target_amount=Decimal("25000"), currency="CHF",
                       target_date=add_months(today, 18),
                       account_id=acc["save"].id, priority=2))
    db.add(SavingsGoal(name="Trip to Morocco (demo)",
                       target_amount=Decimal("15000"), currency="MAD",
                       target_date=add_months(today, 8),
                       saved_amount=Decimal("4000"), priority=1))
    db.commit()
    return {"accounts": len(acc), "transactions": len(txns)}


def remove_demo(db: Session) -> dict:
    """Delete everything created by ``seed_demo``.

    Parameters
    ----------
    db : Session
        The open database session.

    Returns
    -------
    dict
        The number of removed demo accounts.
    """
    ids = list(db.scalars(select(Account.id).where(
        Account.is_demo.is_(True))))
    db.execute(delete(SavingsGoal).where(
        SavingsGoal.name.like("%(demo)")))
    db.execute(delete(Budget).where(Budget.notes == "demo"))
    db.execute(delete(ExchangeRate).where(ExchangeRate.source == "demo"))
    db.execute(delete(RecurringItem).where(RecurringItem.account_id.in_(
        ids)))
    db.execute(delete(Account).where(Account.id.in_(ids)))
    db.commit()
    return {"removed_accounts": len(ids)}
