"""Pydantic request/response schemas.

Money is accepted as ``Decimal`` and serialised to JSON as a number.
"""
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel, ConfigDict, Field, PlainSerializer, field_validator)

Money = Annotated[Decimal, PlainSerializer(float, return_type=float,
                                           when_used="json")]
Currency = Annotated[str, Field(min_length=3, max_length=3,
                                pattern=r"^[A-Za-z]{3}$")]
AccountType = Literal["checking", "savings", "cash", "credit_card",
                      "investment", "loan"]
Frequency = Literal["weekly", "biweekly", "monthly", "quarterly", "yearly"]
AssetClass = Literal["stock", "etf", "bond", "fund", "crypto",
                     "real_estate", "commodity", "cash", "other"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _UpperCurrency(BaseModel):
    @field_validator("currency", "from_currency", "to_currency",
                     mode="before", check_fields=False)
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else v


# --- settings & fx ---------------------------------------------------------
class SettingsOut(BaseModel):
    base_currency: str
    currencies_in_use: list[str]
    schema_version: int
    fx_auto_update: bool = True
    fx_last_update: str | None = None


class SettingsIn(_UpperCurrency):
    base_currency: Currency
    fx_auto_update: bool | None = None


class FxRateIn(_UpperCurrency):
    rate_date: date
    from_currency: Currency
    to_currency: Currency
    rate: Annotated[Decimal, Field(gt=0)]
    source: str = "manual"


class FxRateOut(FxRateIn, ORM):
    id: int
    rate: Money


# --- accounts & categories -------------------------------------------------
class AccountIn(_UpperCurrency):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    type: AccountType
    currency: Currency
    institution: str | None = None
    opening_balance: Decimal = Decimal("0")
    opening_date: date
    is_archived: bool = False
    notes: str | None = None


class AccountOut(ORM):
    id: int
    name: str
    type: str
    currency: str
    institution: str | None
    opening_balance: Money
    opening_date: date
    is_archived: bool
    is_demo: bool
    notes: str | None
    balance: float = 0.0
    balance_base: float | None = None
    holdings_base: float = 0.0


class CategoryIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    kind: Literal["income", "expense"]
    parent_id: int | None = None
    color: str | None = None


class CategoryOut(CategoryIn, ORM):
    id: int
    full_name: str = ""


class RuleIn(BaseModel):
    pattern: Annotated[str, Field(min_length=1, max_length=200)]
    match_field: Literal["description", "merchant", "any"] = "any"
    is_regex: bool = False
    category_id: int
    priority: int = 0


class RuleOut(RuleIn, ORM):
    id: int


# --- transactions ----------------------------------------------------------
class TransactionIn(BaseModel):
    account_id: int
    txn_date: date
    amount: Decimal
    kind: Literal["income", "expense"] | None = None
    description: str = ""
    merchant: str | None = None
    category_id: int | None = None
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def _nonzero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("Amount must not be zero.")
        return v


class TransactionPatch(BaseModel):
    txn_date: date | None = None
    amount: Decimal | None = None
    kind: Literal["income", "expense"] | None = None
    description: str | None = None
    merchant: str | None = None
    category_id: int | None = None
    notes: str | None = None
    clear_category: bool = False


class TransactionOut(ORM):
    id: int
    account_id: int
    account_name: str = ""
    currency: str = ""
    txn_date: date
    amount: Money
    amount_base: float | None = None
    kind: str
    description: str
    merchant: str | None
    category_id: int | None
    category_name: str | None = None
    transfer_group: uuid.UUID | None
    import_batch_id: int | None
    trade_id: int | None
    notes: str | None


class TransactionPage(BaseModel):
    total: int
    items: list[TransactionOut]


class TransferIn(BaseModel):
    from_account_id: int
    to_account_id: int
    txn_date: date
    amount: Annotated[Decimal, Field(gt=0)]
    to_amount: Annotated[Decimal | None, Field(gt=0)] = None
    description: str = "Transfer"


class BulkCategorize(BaseModel):
    ids: list[int]
    category_id: int | None


# --- import ----------------------------------------------------------------
class ImportMapping(BaseModel):
    account_id: int
    date_column: str
    description_column: str
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None
    merchant_column: str | None = None
    date_format: str | None = None
    dayfirst: bool = True
    decimal: Literal[".", ","] = "."
    invert_sign: bool = False
    skip_rows: int = 0


class ImportPreview(BaseModel):
    filename: str
    sha256: str
    already_imported: bool
    delimiter: str
    encoding: str
    columns: list[str]
    rows: list[dict[str, str | None]]
    guess: dict[str, str | bool | None]
    preset: dict | None = None


class ImportResult(BaseModel):
    batch_id: int
    rows_total: int
    rows_imported: int
    rows_duplicate: int
    rows_failed: int
    errors: list[str]
    categorized: int
    preset: str | None = None


class ImportBatchOut(ORM):
    id: int
    account_id: int
    filename: str
    sha256: str
    rows_total: int
    rows_imported: int
    rows_duplicate: int
    rows_failed: int
    imported_at: object


# --- planning --------------------------------------------------------------
class RecurringIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    account_id: int
    category_id: int | None = None
    amount: Decimal
    frequency: Frequency
    start_date: date
    end_date: date | None = None
    is_active: bool = True


class RecurringOut(RecurringIn, ORM):
    id: int
    amount: Money
    next_date: date | None = None


class BudgetIn(BaseModel):
    category_id: int
    monthly_amount: Annotated[Decimal, Field(gt=0)]
    notes: str | None = None


class BudgetOut(BudgetIn, ORM):
    id: int
    monthly_amount: Money


class GoalIn(_UpperCurrency):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    target_amount: Annotated[Decimal, Field(gt=0)]
    currency: Currency
    target_date: date | None = None
    account_id: int | None = None
    saved_amount: Decimal = Decimal("0")
    priority: int = 0
    notes: str | None = None


# --- investments -----------------------------------------------------------
class HoldingIn(_UpperCurrency):
    account_id: int
    symbol: Annotated[str, Field(min_length=1, max_length=32)]
    name: Annotated[str, Field(min_length=1, max_length=160)]
    asset_class: AssetClass
    currency: Currency
    notes: str | None = None


class TradeIn(BaseModel):
    trade_date: date
    trade_type: Literal["buy", "sell", "dividend", "fee"]
    quantity: Annotated[Decimal, Field(ge=0)] = Decimal("0")
    price: Annotated[Decimal, Field(ge=0)] = Decimal("0")
    fees: Annotated[Decimal, Field(ge=0)] = Decimal("0")
    cash_amount: Annotated[Decimal | None, Field(ge=0)] = None
    affects_cash: bool = True
    notes: str | None = None


class TradeOut(ORM):
    id: int
    holding_id: int
    trade_date: date
    trade_type: str
    quantity: Money
    price: Money
    fees: Money
    cash_amount: Money | None
    notes: str | None


class PriceIn(BaseModel):
    price_date: date
    price: Annotated[Decimal, Field(ge=0)]
    source: str = "manual"


class PriceOut(PriceIn, ORM):
    id: int
    holding_id: int
    price: Money
