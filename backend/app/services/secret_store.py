"""Keep a small secret (the backup password) outside the database.

On Windows the value is encrypted with DPAPI for the current user, so the
file is useless on another account or PC. Elsewhere (development, tests)
it is written with owner-only permissions.
"""
import base64
import ctypes
import os
import sys
from pathlib import Path

_PREFIX_DPAPI = b"dpapi:"
_PREFIX_PLAIN = b"plain:"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0,
            ctypes.byref(blob_out))
    if not ok:
        raise OSError(
            "Windows could not protect or unprotect the saved backup "
            "password (DPAPI). Set the backup password again in Settings.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def save(path: Path, value: str | None) -> None:
    """Store ``value`` in ``path``; ``None`` removes the file.

    Parameters
    ----------
    path : Path
        The file that holds the secret.
    value : str or None
        The secret to keep.
    """
    path = Path(path)
    if value is None:
        path.unlink(missing_ok=True)
        return
    raw = value.encode("utf-8")
    if sys.platform == "win32":
        data = _PREFIX_DPAPI + base64.b64encode(_dpapi(raw, True))
    else:
        data = _PREFIX_PLAIN + base64.b64encode(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load(path: Path) -> str | None:
    """Return the secret stored in ``path``, or ``None`` if there is none.

    Parameters
    ----------
    path : Path
        The file that holds the secret.
    """
    path = Path(path)
    if not path.is_file():
        return None
    data = path.read_bytes()
    if data.startswith(_PREFIX_DPAPI):
        return _dpapi(base64.b64decode(data[len(_PREFIX_DPAPI):]),
                      False).decode("utf-8")
    if data.startswith(_PREFIX_PLAIN):
        return base64.b64decode(data[len(_PREFIX_PLAIN):]).decode("utf-8")
    return None
