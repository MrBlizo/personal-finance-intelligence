"""List interface texts that have no French or Arabic translation yet.

Scans ``t("...")`` calls and ``label: "..."`` entries in the Windows
screens and compares them with ``frontend/lib/locales/{fr,ar}.json``.

Usage::

    python scripts/i18n/missing.py            # print missing keys
    python scripts/i18n/missing.py --json     # as a JSON list
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "frontend"
CALL = re.compile(r"""\bt\(\s*(["'])((?:\\.|(?!\1).)*)\1""")
LABEL = re.compile(r"""\blabel:\s*(["'])((?:\\.|(?!\1).)*)\1""")


def used_keys():
    """Return the set of literal keys passed to ``t()`` or used as labels.

    Returns
    -------
    set of str
        The interface texts found in ``frontend/app`` and
        ``frontend/components``.
    """
    keys = set()
    for folder in ("app", "components"):
        for path in (FRONT / folder).rglob("*.tsx"):
            text = path.read_text(encoding="utf-8")
            for rx in (CALL, LABEL):
                for _, key in rx.findall(text):
                    keys.add(key.encode().decode("unicode_escape")
                             if "\\u" in key else key.replace('\\"', '"'))
    return keys


def main():
    parser = argparse.ArgumentParser(
        description="List interface texts missing from the French or "
                    "Arabic translation files.",
        epilog="Example: python scripts/i18n/missing.py --json")
    parser.add_argument("--json", action="store_true",
                        help="Print the missing keys as a JSON list.")
    args = parser.parse_args()
    keys = used_keys()
    missing = set()
    for lang in ("fr", "ar"):
        path = FRONT / "lib" / "locales" / f"{lang}.json"
        table = json.loads(path.read_text(encoding="utf-8"))
        missing |= {k for k in keys if k not in table}
    out = sorted(missing)
    print(json.dumps(out, ensure_ascii=False, indent=1) if args.json
          else "\n".join(out))


if __name__ == "__main__":
    main()
