"""Subset Material Symbols Rounded to the icons the Windows screens use.

The full variable font is about 5 MB; the app needs a few dozen glyphs.
This reads the code points from ``frontend/components/icons.ts`` and writes
``frontend/public/fonts/material-symbols-rounded.woff2`` with only those
glyphs, keeping the FILL and wght axes (filled icons mark the selected
destination) and pinning GRAD and opsz to their defaults.

Usage::

    python scripts/m3/subset-icons.py

Requires ``fonttools`` and ``brotli``.
"""
import argparse
import re
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def code_points(icons_ts):
    """Return the code points listed in the icon map.

    Parameters
    ----------
    icons_ts : pathlib.Path
        The TypeScript module that maps icon names to code points.

    Returns
    -------
    list of int
        The code points, sorted.
    """
    text = icons_ts.read_text(encoding="utf-8")
    hexes = re.findall(r"\\u([0-9a-fA-F]{4})", text)
    found = sorted({int(h, 16) for h in hexes})
    if not found:
        raise SystemExit(
            f"No code points found in {icons_ts}. The icon map should hold "
            "entries like `home: \"\\ue88a\"`; check that the file was not "
            "emptied or reformatted.")
    return found


def main():
    parser = argparse.ArgumentParser(
        description="Subset Material Symbols Rounded to the icons in "
                    "frontend/components/icons.ts.",
        epilog="Example: python scripts/m3/subset-icons.py")
    parser.add_argument(
        "--source", type=Path,
        default=FRONTEND / "node_modules/material-symbols/"
                           "material-symbols-rounded.woff2",
        help="Full Material Symbols Rounded font (from the material-symbols "
             "npm package).")
    parser.add_argument(
        "--out", type=Path,
        default=FRONTEND / "public/fonts/material-symbols-rounded.woff2",
        help="Where to write the subset font.")
    args = parser.parse_args()
    if not args.source.exists():
        raise SystemExit(
            f"{args.source} does not exist. Run `npm ci` in frontend/ so the "
            "material-symbols package is installed, or pass --source.")
    cps = code_points(FRONTEND / "components/icons.ts")
    font = TTFont(args.source)
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = []
    options.notdef_outline = True
    options.name_IDs = ["*"]
    sub = subset.Subsetter(options)
    sub.populate(unicodes=cps)
    sub.subset(font)
    font = instancer.instantiateVariableFont(font, {"GRAD": 0, "opsz": 24})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    font.flavor = "woff2"
    font.save(args.out)
    size = args.out.stat().st_size / 1024
    print(f"wrote {args.out.relative_to(ROOT)}: {len(cps)} icons, "
          f"{size:.0f} KB")


if __name__ == "__main__":
    main()
