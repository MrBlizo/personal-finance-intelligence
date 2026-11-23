"""Adjust the Gradle files that ``flutter create`` generates in CI.

- flutter_local_notifications needs core library desugaring (java.time on
  old Android versions), enabled in ``android/app/build.gradle.kts``.
- Release builds are not shrunk with R8 (``shrink=false`` in
  ``android/gradle.properties``): R8 broke ML Kit's text recognition in
  1.0.0 (a NullPointerException inside ML Kit when scanning a receipt).

The generated files are not in the repository, so CI runs this script after
``flutter create``.

Usage: python tool/patch_android.py android/app/build.gradle.kts
"""
import sys
from pathlib import Path

DESUGAR = 'coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")'


def patch(path: Path) -> None:
    """Enable core library desugaring in the app's Gradle file.

    Parameters
    ----------
    path : Path
        The ``build.gradle.kts`` of the Android app module.

    Raises
    ------
    SystemExit
        If the file has no ``compileOptions`` block to extend; regenerate
        the platform folder with ``flutter create`` and run again.
    """
    text = path.read_text(encoding="utf-8")
    if "isCoreLibraryDesugaringEnabled" not in text:
        if "compileOptions {" not in text:
            raise SystemExit(
                f"{path} has no compileOptions block, so desugaring could not "
                "be enabled. Regenerate it with 'flutter create .' and run "
                "this script again.")
        text = text.replace(
            "compileOptions {",
            "compileOptions {\n"
            "        isCoreLibraryDesugaringEnabled = true", 1)
    if DESUGAR not in text:
        text += f"\ndependencies {{\n    {DESUGAR}\n}}\n"
    path.write_text(text, encoding="utf-8")
    print(f"patched {path}")


def no_shrink(properties: Path) -> None:
    """Turn off R8 shrinking for release builds.

    Parameters
    ----------
    properties : Path
        The ``gradle.properties`` of the Android project; created if missing.
    """
    text = ""
    if properties.exists():
        text = properties.read_text(encoding="utf-8")
    if "shrink=" not in text:
        text = (text.rstrip("\n")
                + "\n# ML Kit fails after R8 shrinking.\nshrink=false\n")
        properties.write_text(text.lstrip("\n"), encoding="utf-8")
    print(f"patched {properties}")


if __name__ == "__main__":
    app_gradle = Path(sys.argv[1] if len(sys.argv) > 1
                      else "android/app/build.gradle.kts")
    patch(app_gradle)
    no_shrink(app_gradle.parent.parent / "gradle.properties")
