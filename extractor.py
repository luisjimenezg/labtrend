"""
PDF extraction for clinical lab reports.
Parses text from PDFs and extracts date + parameter table rows.

The parsing is heuristic and may need tuning for specific lab report formats.
Run:  python extractor.py <path/to/file.pdf>
to inspect what gets extracted before importing into the database.
"""
import re
import sys
from pathlib import Path

import pdfplumber

# --- Date detection --------------------------------------------------------
# Matches common Spanish/European date formats: 15/03/2024, 15-03-2024, 15.03.2024
# and ISO: 2024-03-15
_DATE_PATTERNS = [
    (r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b", "DMY"),
    (r"\b(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})\b", "YMD"),
]


def _find_date(text: str) -> str | None:
    """Return the first date found as ISO string YYYY-MM-DD, or None."""
    for pattern, order in _DATE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            if order == "DMY":
                d, mo, y = m.group(1), m.group(2), m.group(3)
            else:
                y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


# --- Parameter detection ---------------------------------------------------
# Tries to capture lines like:
#   Glucosa          95       mg/dL     70-110
#   Hemoglobina A1c  6.2   %   <6.5
_PARAM_RE = re.compile(
    r"^(?P<name>[A-Za-záéíóúÁÉÍÓÚüÜñÑ][A-Za-záéíóúÁÉÍÓÚüÜñÑ0-9 \-/().]+?)"
    r"\s{2,}"
    r"(?P<value>[0-9]+(?:[.,][0-9]+)?)"
    r"(?:\s+(?P<unit>[a-zA-Z/%µgdLmolUIUfl]+))?"
    r"(?:\s+(?P<ref_range>[<>]?\s*\d[\d\s\-.,/<>]+))?"
    r"\s*$",
    re.MULTILINE,
)


def _parse_parameters(text: str) -> list[dict]:
    params = []
    for m in _PARAM_RE.finditer(text):
        value_str = m.group("value").replace(",", ".")
        try:
            value = float(value_str)
        except ValueError:
            continue
        params.append({
            "name": m.group("name").strip(),
            "value": value,
            "unit": (m.group("unit") or "").strip() or None,
            "ref_range": (m.group("ref_range") or "").strip() or None,
        })
    return params


# --- Public API ------------------------------------------------------------

def extract(pdf_path: str | Path) -> dict:
    """
    Extract date and parameters from a lab PDF.
    Returns {"date": "YYYY-MM-DD", "parameters": [...]} or raises ValueError.
    """
    pdf_path = Path(pdf_path)
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text += (page.extract_text() or "") + "\n"

    date = _find_date(full_text)
    if not date:
        raise ValueError(f"Could not find a date in {pdf_path.name}")

    parameters = _parse_parameters(full_text)
    return {"date": date, "parameters": parameters}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extractor.py <file.pdf>")
        sys.exit(1)
    result = extract(sys.argv[1])
    print(f"Date: {result['date']}")
    print(f"Parameters found: {len(result['parameters'])}")
    for p in result["parameters"]:
        print(f"  {p['name']}: {p['value']} {p['unit'] or ''} (ref: {p['ref_range'] or '-'})")
