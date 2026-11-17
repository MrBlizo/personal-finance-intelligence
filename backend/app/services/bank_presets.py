"""Built-in CSV layouts of common US banks and card issuers.

A layout is recognised from the column names of the file, so a bank that
adds a column later is still matched. Users can still change any setting
in the preview; a mapping they save for a file wins over these.
The layouts follow the banks' download formats as of late 2026 and are
checked by tests with sample headers, not with live bank files.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BankLayout:
    """One bank's CSV download format."""

    name: str
    required: tuple[str, ...]
    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None
    merchant: str | None = None
    invert_sign: bool = False
    extra: dict = field(default_factory=dict)


# More specific layouts first: the first full match wins.
LAYOUTS: tuple[BankLayout, ...] = (
    BankLayout("Apple Card", ("transaction date", "clearing date",
               "description", "merchant", "amount (usd)"),
               "Transaction Date", "Description", amount="Amount (USD)",
               merchant="Merchant", invert_sign=True),
    BankLayout("Chase credit card", ("transaction date", "post date",
               "description", "category", "type", "amount"),
               "Transaction Date", "Description", amount="Amount"),
    BankLayout("Chase checking", ("details", "posting date", "description",
               "amount", "type", "balance"),
               "Posting Date", "Description", amount="Amount"),
    BankLayout("Capital One credit card", ("transaction date",
               "posted date", "card no.", "description", "debit", "credit"),
               "Transaction Date", "Description", debit="Debit",
               credit="Credit"),
    BankLayout("Citi credit card", ("status", "date", "description",
               "debit", "credit"),
               "Date", "Description", debit="Debit", credit="Credit"),
    BankLayout("Discover", ("trans. date", "post date", "description",
               "amount", "category"),
               "Trans. Date", "Description", amount="Amount",
               invert_sign=True),
    BankLayout("Bank of America credit card", ("posted date",
               "reference number", "payee", "address", "amount"),
               "Posted Date", "Payee", amount="Amount"),
    BankLayout("Bank of America checking", ("date", "description", "amount",
               "running bal."),
               "Date", "Description", amount="Amount"),
    BankLayout("U.S. Bank", ("date", "transaction", "name", "memo",
               "amount"),
               "Date", "Name", amount="Amount", merchant="Name"),
    BankLayout("Ally Bank", ("date", "time", "amount", "type",
               "description"),
               "Date", "Description", amount="Amount"),
    BankLayout("American Express", ("date", "description", "amount"),
               "Date", "Description", amount="Amount", invert_sign=True,
               extra={"also_one_of": ("card member", "account #",
                                      "extended details")}),
    BankLayout("Wells Fargo", ("date", "amount", "flag", "check",
               "description"),
               "Date", "Description", amount="Amount"),
)

# Wells Fargo files have no header row; the importer names the columns.
HEADERLESS_5 = ["Date", "Amount", "Flag", "Check", "Description"]


def match(columns: list[str]) -> dict | None:
    """Return the built-in mapping for a known bank layout.

    Parameters
    ----------
    columns : list of str
        The column names of the CSV file, as read.

    Returns
    -------
    dict or None
        ``{"name": ..., "mapping": {...}}`` with the file's own column
        names, or None when no layout matches.
    """
    actual = {c.strip().lower(): c for c in columns}
    for lay in LAYOUTS:
        if not all(r in actual for r in lay.required):
            continue
        alt = lay.extra.get("also_one_of")
        if alt and not any(a in actual for a in alt):
            continue

        def col(name: str | None) -> str | None:
            return actual.get(name.lower()) if name else None

        return {"id": None, "name": lay.name, "builtin": True, "mapping": {
            "date_column": col(lay.date),
            "description_column": col(lay.description),
            "amount_column": col(lay.amount),
            "debit_column": col(lay.debit),
            "credit_column": col(lay.credit),
            "merchant_column": col(lay.merchant),
            "date_format": None, "dayfirst": False, "decimal": ".",
            "invert_sign": lay.invert_sign}}
    return None
