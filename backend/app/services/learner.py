"""Category suggestions learned from the user's own categorised history.

A multinomial naive Bayes model over normalised words of the description
and merchant. It is deliberately simple and transparent: every suggestion
can be explained by the words that pushed it towards its category.

Training data are categorised, non-transfer transactions whose category
was *not* set by this model (``category_source != 'model'``), so the
model never learns from its own guesses.

Validation is chronological: the model is trained on the oldest 80 % of
examples and scored on the newest 20 %, which mimics how it is used
(predicting future transactions from past ones) and avoids the optimistic
bias of a random split. The score is compared against the baseline of
always predicting the most frequent category.
"""
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Category, Transaction

MIN_EXAMPLES = 20
ALPHA = 1.0
_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
_STOP = {"the", "and", "for", "von", "und", "der", "die", "das", "les",
         "des", "pour", "sur", "card", "karte", "debit", "credit", "payment",
         "zahlung", "paiement", "achat", "purchase", "chf", "eur", "usd",
         "mad", "twint", "pos", "ref"}


def tokens(description: str, merchant: str | None, amount: float) -> list[str]:
    """Turn a transaction into model features.

    Parameters
    ----------
    description : str
        The bank description text.
    merchant : str or None
        The merchant or payee, when known.
    amount : float
        The signed amount; only its sign is used.

    Returns
    -------
    list of str
        Lower-case words (digits and very common words removed) plus a
        sign feature.
    """
    text = f"{description or ''} {merchant or ''}".lower()
    words = [w for w in _WORD.findall(text) if w not in _STOP]
    if merchant:
        words.append("m:" + merchant.strip().lower()[:40])
    words.append("sign:+" if amount > 0 else "sign:-")
    return words


@dataclass
class Model:
    """A fitted naive Bayes model."""

    class_count: Counter = field(default_factory=Counter)
    word_count: dict = field(default_factory=lambda: defaultdict(Counter))
    total_words: Counter = field(default_factory=Counter)
    vocab: set = field(default_factory=set)
    n: int = 0

    def fit(self, rows: list[tuple[list[str], int]]) -> "Model":
        for words, cat in rows:
            self.class_count[cat] += 1
            self.word_count[cat].update(words)
            self.total_words[cat] += len(words)
            self.vocab.update(words)
            self.n += 1
        return self

    def _log_scores(self, words: list[str], allowed: set[int] | None
                    ) -> dict[int, float]:
        v = len(self.vocab) or 1
        scores = {}
        for cat, cnt in self.class_count.items():
            if allowed is not None and cat not in allowed:
                continue
            s = math.log(cnt / self.n)
            denom = self.total_words[cat] + ALPHA * v
            wc = self.word_count[cat]
            for w in words:
                if w in self.vocab:
                    s += math.log((wc[w] + ALPHA) / denom)
            scores[cat] = s
        return scores

    def predict(self, words: list[str], allowed: set[int] | None = None
                ) -> tuple[int | None, float, list[str]]:
        """Return the best category, its probability and the key words.

        Parameters
        ----------
        words : list of str
            The features from :func:`tokens`.
        allowed : set of int, optional
            The categories that may be predicted (e.g. only expense
            categories for a negative amount).

        Returns
        -------
        tuple
            The category id (or None), its posterior probability and up to
            three words that favoured it most over the runner-up.
        """
        scores = self._log_scores(words, allowed)
        if not scores:
            return None, 0.0, []
        top = max(scores.values())
        exp = {c: math.exp(s - top) for c, s in scores.items()}
        z = sum(exp.values())
        ranked = sorted(exp, key=exp.get, reverse=True)
        best = ranked[0]
        why: list[str] = []
        if len(ranked) > 1:
            second = ranked[1]
            v = len(self.vocab) or 1
            d1 = self.total_words[best] + ALPHA * v
            d2 = self.total_words[second] + ALPHA * v
            gain = {}
            for w in set(words):
                if w in self.vocab and not w.startswith("sign:"):
                    gain[w] = (math.log((self.word_count[best][w] + ALPHA) / d1)
                               - math.log((self.word_count[second][w]
                                           + ALPHA) / d2))
            why = [w.removeprefix("m:") for w, g in
                   sorted(gain.items(), key=lambda x: -x[1])[:3] if g > 0]
        return best, exp[best] / z, why


def _examples(db: Session) -> list[tuple[date, list[str], int]]:
    stmt = (select(Transaction.txn_date, Transaction.description,
                   Transaction.merchant, Transaction.amount,
                   Transaction.category_id)
            .where(Transaction.category_id.is_not(None),
                   Transaction.kind != "transfer",
                   (Transaction.category_source.is_(None))
                   | (Transaction.category_source != "model"))
            .order_by(Transaction.txn_date, Transaction.id))
    return [(d, tokens(desc, m, float(a)), c)
            for d, desc, m, a, c in db.execute(stmt)]


def _allowed(kinds: dict[int, str], amount: float) -> set[int]:
    want = "income" if amount > 0 else "expense"
    return {c for c, k in kinds.items() if k == want}


def train(db: Session) -> Model | None:
    """Fit the model on all eligible history, or None if too little."""
    ex = _examples(db)
    if len(ex) < MIN_EXAMPLES or len({c for _, _, c in ex}) < 2:
        return None
    return Model().fit([(w, c) for _, w, c in ex])


def evaluate(db: Session, threshold: float) -> dict:
    """Score the model with a chronological 80/20 split.

    Parameters
    ----------
    db : Session
        The open database session.
    threshold : float
        The confidence above which suggestions are applied automatically.

    Returns
    -------
    dict
        Sample sizes, accuracy, the most-frequent-category baseline, and
        the share and accuracy of predictions above ``threshold``. Values
        are None when there is not enough history to evaluate.
    """
    ex = _examples(db)
    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    out = {"examples": len(ex), "min_examples": MIN_EXAMPLES,
           "n_train": 0, "n_test": 0, "accuracy": None, "baseline": None,
           "coverage_at_threshold": None, "accuracy_at_threshold": None,
           "threshold": threshold, "categories": len({c for *_, c in ex})}
    if len(ex) < MIN_EXAMPLES or out["categories"] < 2:
        return out
    cut = int(len(ex) * 0.8)
    trn, tst = ex[:cut], ex[cut:]
    model = Model().fit([(w, c) for _, w, c in trn])
    common = Counter(c for *_, c in trn).most_common(1)[0][0]
    hits = base = conf_n = conf_hits = 0
    for _, words, cat in tst:
        sign = 1.0 if "sign:+" in words else -1.0
        pred, p, _ = model.predict(words, _allowed(kinds, sign))
        hits += pred == cat
        base += common == cat
        if p >= threshold:
            conf_n += 1
            conf_hits += pred == cat
    n = len(tst)
    out.update(n_train=len(trn), n_test=n, accuracy=hits / n,
               baseline=base / n, coverage_at_threshold=conf_n / n,
               accuracy_at_threshold=(conf_hits / conf_n if conf_n
                                      else None))
    return out


def suggest(db: Session, txns: list[Transaction],
            model: Model | None = None) -> dict[int, dict]:
    """Suggest categories for the given transactions.

    Parameters
    ----------
    db : Session
        The open database session.
    txns : list of Transaction
        The transactions to classify (normally uncategorised ones).
    model : Model, optional
        A fitted model; trained on the fly when omitted.

    Returns
    -------
    dict of int to dict
        Per transaction id: ``category_id``, ``confidence`` and ``why``.
        Empty when there is not enough history.
    """
    model = model or train(db)
    if model is None:
        return {}
    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    out = {}
    for t in txns:
        amount = float(t.amount)
        cat, p, why = model.predict(tokens(t.description, t.merchant, amount),
                                    _allowed(kinds, amount))
        if cat is not None:
            out[t.id] = {"category_id": cat, "confidence": p, "why": why}
    return out
