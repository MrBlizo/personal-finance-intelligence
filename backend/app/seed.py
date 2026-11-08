"""Default categories and settings inserted into a new database."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Category, Setting

PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9",
           "#CC79A7", "#F0E442", "#BE1818", "#6B7280", "#7C3AED",
           "#0F766E", "#9A3412"]

DEFAULT_CATEGORIES: dict[str, dict[str, list[str]]] = {
    "income": {
        "Salary": [], "Bonus": [], "Freelance": [], "Investment Income":
        ["Dividends", "Interest"], "Gifts Received": [], "Refunds": [],
        "Other Income": []},
    "expense": {
        "Housing": ["Rent", "Utilities", "Internet & Phone",
                    "Household Insurance"],
        "Food": ["Groceries", "Restaurants", "Coffee & Snacks"],
        "Transport": ["Public Transport", "Fuel", "Car", "Taxi & Rides"],
        "Health": ["Health Insurance", "Doctor & Dentist", "Pharmacy"],
        "Shopping": ["Clothing", "Electronics", "Home & Garden"],
        "Leisure": ["Entertainment", "Subscriptions", "Sports", "Travel"],
        "Education": ["Courses", "Books"],
        "Finance": ["Bank Fees", "Taxes", "Other Insurance"],
        "Family & Gifts": ["Gifts", "Donations"],
        "Other Expense": [],
    },
}


def get_setting(db: Session, key: str, default: str) -> str:
    """Return a stored setting value, or ``default`` when it is absent.

    Parameters
    ----------
    db : Session
        The open database session.
    key : str
        The setting key.
    default : str
        The value returned when the key is not stored.

    Returns
    -------
    str
        The stored or default value.
    """
    row = db.get(Setting, key)
    return row.value if row else default


def seed_defaults(db: Session, base_currency: str) -> None:
    """Insert default settings and categories if the database is empty.

    Parameters
    ----------
    db : Session
        The open database session.
    base_currency : str
        The ISO 4217 code used as reporting currency for a new database.
    """
    if db.get(Setting, "base_currency") is None:
        db.add(Setting(key="base_currency", value=base_currency))
    if db.scalar(select(Category.id).limit(1)) is None:
        i = 0
        for kind, groups in DEFAULT_CATEGORIES.items():
            for parent_name, children in groups.items():
                color = PALETTE[i % len(PALETTE)]
                i += 1
                parent = Category(name=parent_name, kind=kind, color=color)
                db.add(parent)
                db.flush()
                for child in children:
                    db.add(Category(name=child, kind=kind, color=color,
                                    parent_id=parent.id))
    db.commit()
