"""ORM models for Personal Finance Intelligence.

Sign convention: ``Transaction.amount`` is signed in the account currency.
Positive values are money flowing into the account, negative values are
money flowing out. Money is stored as ``NUMERIC`` (exact decimal).
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ACCOUNT_TYPES = ("checking", "savings", "cash", "credit_card",
                 "investment", "loan")
LIQUID_TYPES = ("checking", "savings", "cash", "credit_card")
CATEGORY_KINDS = ("income", "expense")
TXN_KINDS = ("income", "expense", "transfer")
FREQUENCIES = ("weekly", "biweekly", "monthly", "quarterly", "yearly")
ASSET_CLASSES = ("stock", "etf", "bond", "fund", "crypto", "real_estate",
                 "commodity", "cash", "other")
TRADE_TYPES = ("buy", "sell", "dividend", "fee")
MATCH_FIELDS = ("description", "merchant", "any")

Money = Numeric(14, 2)


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class ExchangeRate(Base):
    """One unit of ``from_currency`` equals ``rate`` units of
    ``to_currency`` on ``rate_date``."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("rate_date", "from_currency", "to_currency"),
        CheckConstraint("rate > 0", name="ck_rate_positive"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, index=True)
    from_currency: Mapped[str] = mapped_column(String(3))
    to_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    source: Mapped[str] = mapped_column(String(50), default="manual")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint(_in("type", ACCOUNT_TYPES),
                                      name="ck_account_type"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    type: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    institution: Mapped[str | None] = mapped_column(String(120))
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=0)
    opening_date: Mapped[date] = mapped_column(Date)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("name", "kind"),
        CheckConstraint(_in("kind", CATEGORY_KINDS), name="ck_cat_kind"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"))
    color: Mapped[str | None] = mapped_column(String(9))
    parent: Mapped["Category | None"] = relationship(remote_side=[id])


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(260))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    archived_path: Mapped[str] = mapped_column(String(500))
    mapping_json: Mapped[str] = mapped_column(Text)
    rows_total: Mapped[int] = mapped_column(Integer)
    rows_imported: Mapped[int] = mapped_column(Integer)
    rows_duplicate: Mapped[int] = mapped_column(Integer)
    rows_failed: Mapped[int] = mapped_column(Integer)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class ImportPreset(Base):
    """A saved CSV column mapping, recognised by the file's header row."""

    __tablename__ = "import_presets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    header_signature: Mapped[str] = mapped_column(String(64), index=True)
    mapping_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("account_id", "symbol"),
        CheckConstraint(_in("asset_class", ASSET_CLASSES),
                        name="ck_asset_class"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    asset_class: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    notes: Mapped[str | None] = mapped_column(Text)
    account: Mapped[Account] = relationship()


class InvestmentTrade(Base):
    __tablename__ = "investment_trades"
    __table_args__ = (
        CheckConstraint(_in("trade_type", TRADE_TYPES), name="ck_trade"),
        CheckConstraint("quantity >= 0", name="ck_trade_qty"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    holding_id: Mapped[int] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    trade_type: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    fees: Mapped[Decimal] = mapped_column(Money, default=0)
    cash_amount: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)


class AssetPrice(Base):
    __tablename__ = "asset_prices"
    __table_args__ = (UniqueConstraint("holding_id", "price_date"),
                      CheckConstraint("price >= 0", name="ck_price"))
    id: Mapped[int] = mapped_column(primary_key=True)
    holding_id: Mapped[int] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), index=True)
    price_date: Mapped[date] = mapped_column(Date)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    source: Mapped[str] = mapped_column(String(50), default="manual")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "fingerprint"),
        CheckConstraint(_in("kind", TXN_KINDS), name="ck_txn_kind"),
        CheckConstraint("amount <> 0", name="ck_txn_nonzero"),
        Index("ix_txn_account_date", "account_id", "txn_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"))
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    kind: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(500), default="")
    merchant: Mapped[str | None] = mapped_column(String(200))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    transfer_group: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, index=True)
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"))
    trade_id: Mapped[int | None] = mapped_column(
        ForeignKey("investment_trades.id", ondelete="CASCADE"))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now())
    account: Mapped[Account] = relationship()
    category: Mapped[Category | None] = relationship()


class CategoryRule(Base):
    __tablename__ = "category_rules"
    __table_args__ = (CheckConstraint(_in("match_field", MATCH_FIELDS),
                                      name="ck_rule_field"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(200))
    match_field: Mapped[str] = mapped_column(String(12), default="any")
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(Integer, default=0)


class RecurringItem(Base):
    __tablename__ = "recurring_items"
    __table_args__ = (
        CheckConstraint(_in("frequency", FREQUENCIES), name="ck_freq"),
        CheckConstraint("amount <> 0", name="ck_rec_nonzero"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"))
    amount: Mapped[Decimal] = mapped_column(Money)
    frequency: Mapped[str] = mapped_column(String(10))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Budget(Base):
    """Monthly spending limit for an expense category, in base currency."""

    __tablename__ = "budgets"
    __table_args__ = (CheckConstraint("monthly_amount > 0",
                                      name="ck_budget_pos"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), unique=True)
    monthly_amount: Mapped[Decimal] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)
    category: Mapped[Category] = relationship()


class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    __table_args__ = (CheckConstraint("target_amount > 0",
                                      name="ck_goal_pos"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    target_date: Mapped[date | None] = mapped_column(Date)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"))
    saved_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
