import shutil
import tempfile
from pathlib import Path

SAMPLE = 1 << 20


def detect_encoding(path: str | Path) -> str:
    with open(path, "rb") as f:
        raw = f.read(SAMPLE)
    for enc in ("utf-8-sig", "utf-8"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    for enc in ("gbk", "gb18030", "latin-1"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


def ensure_utf8(path: str | Path) -> str:
    enc = detect_encoding(path)
    if enc in ("utf-8", "utf-8-sig"):
        return str(path)
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir=str(Path(path).parent))
    tmp.close()
    with open(path, "r", encoding=enc, errors="replace", newline="") as src, open(
        tmp.name, "w", encoding="utf-8", newline=""
    ) as dst:
        shutil.copyfileobj(src, dst, length=1 << 20)
    return tmp.name


def read_header(path: str | Path) -> list[str]:
    with open(ensure_utf8(path), "r", encoding="utf-8-sig", errors="replace") as f:
        line = f.readline()
    if "\t" in line and line.count("\t") > line.count(","):
        return [c.strip() for c in line.rstrip("\r\n").split("\t")]
    if ";" in line and line.count(";") > line.count(","):
        return [c.strip() for c in line.rstrip("\r\n").split(";")]
    import csv

    return next(csv.reader([line.rstrip("\r\n")]), [])
