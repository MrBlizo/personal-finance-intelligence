# PyInstaller spec for pfi-api.exe (one-folder build: fast start-up).
#   pyinstaller --noconfirm pfi-api.spec   ->   dist/pfi-api/pfi-api.exe
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("app")
    + [
        "sqlalchemy.dialects.postgresql.psycopg",
        "psycopg_binary",
        "multipart",
        "python_multipart",
    ]
    + collect_submodules("reportlab.graphics")
    + collect_submodules("openpyxl")
)
# reportlab ships its standard fonts and glyph metrics as data files.
datas = collect_data_files("reportlab")

a = Analysis(
    ["run.py"],
    pathex=["."],
    hiddenimports=hidden,
    datas=datas,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "notebook",
              "PyQt5", "PySide6", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="pfi-api",
    console=True,          # stdout goes to the log; PFI.exe hides the window
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="pfi-api", upx=False)
