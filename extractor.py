"""
PDF extraction for clinical lab reports.
Supports three formats observed in the data:
  - Hospital HM: "Name   Value   Unit   (low - high)   [*]"
  - Adeslas:     "Name   Value   Unit   (low - high)   AUTO|MML"
  - CentroSalud: "Name   Value   [<>]   RangeLow   RangeHigh   Unit"

Date is taken from the YYYYMMDD filename prefix (most reliable).
Run standalone to inspect extraction before importing to DB:
  python extractor.py pdfs/some_analysis.pdf
"""
import re
import sys
from pathlib import Path

import pdfplumber

# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------

_MONTHS_ES = {
    'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
    'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
    'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12',
}


def _date_from_filename(path: Path) -> str | None:
    m = re.match(r'(\d{4})(\d{2})(\d{2})', path.name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _date_from_text(text: str) -> str | None:
    """Fallback: Spanish month names or numeric formats."""
    m = re.search(
        r'(\d{1,2})\s+(?:de\s+)?(' + '|'.join(_MONTHS_ES) + r')\s+(?:de\s+)?(\d{4})',
        text, re.IGNORECASE,
    )
    if m:
        d, mon, y = m.group(1), m.group(2).lower(), m.group(3)
        return f"{y}-{_MONTHS_ES[mon]}-{int(d):02d}"
    # "Fecha: DD/MM/YYYY" (Adeslas / CentroSalud header)
    m = re.search(r'Fecha[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


# ---------------------------------------------------------------------------
# Parameter line parsing
# ---------------------------------------------------------------------------

# Lines whose first word(s) are known metadata — not clinical parameters.
_SKIP_RE = re.compile(
    r'^\s*(?:'
    r'An.lisis|Resultado|Unidades|Valores|P.gina|Cap.tulo|Informe|Impreso|'
    r'Historia|Dr/a|Edad|Sexo|NIP|Paciente|Fecha|M.dico|Observaciones|'
    r'Sociedad|HEMATOLOGIA|BIOQUIMICA|COAGULACION|ORINA|HORMONAS|PERFIL|'
    r'MICROBIOLOG|SUERO|ESTUDIO|BIOQU|PERFILES|Perfil|'
    r'Muestra|PARCIAL|Destino|Procedencia|Madrid|Validaci|Referencia|'
    r'Imane|Especialista|Remitente|Especialidad|CIAS|'
    r'Nueva t.cnica|Nuevos valores|Debido al|No procede|Intervalo|'
    r'Los valores|Determinaci|Ligera|Frecuentes|'
    r'Comentario|Componente|Prioridad|CIP|NASS|'
    r'Respuesta|CALLE|Laboratorio|Datos|H\. U\.|'
    r'TRAZADORA|COMENTARIOS|INCIDENCIAS|'
    r'Recomendable|Recomendaciones|menor a|mayor a|posponer|'
    r'derivaci|Monitorizar|Estimaci|Trimestre|situaci|'
    r'N\S?\s*extracci|N\S?\s*Anal|C\.S\.'
    r')\b',
    re.IGNORECASE,
)

# Lines containing these strings anywhere are non-result lines.
_SKIP_CONTAINS_RE = re.compile(
    r'\b(Pendiente|Anulado|NEGATIVO(?!\s*:))\b', re.IGNORECASE
)


def _extract_unit_and_range(rest: str) -> tuple[str | None, str | None]:
    """Parse everything after the numeric value into (unit, ref_range).

    Handles three range styles:
    - Parenthetical: "mg/dl (74 - 109)"  →  unit="mg/dl", ref="74 - 109"
    - Trailing sign:  "mg/dL <1.2"        →  unit="mg/dL", ref="<1.2"
    - CentroSalud:    "0.35 4.94 uUI/mL"  →  unit="uUI/mL", ref="0.35-4.94"
    """
    rest = rest.strip()
    if not rest:
        return None, None

    # Style 1: trailing (...)
    m = re.search(r'\(\s*([^)]+?)\s*\)\s*$', rest)
    if m:
        ref_range = m.group(1).strip()
        unit = rest[:m.start()].strip() or None
        return unit, ref_range

    # Style 2: trailing <N or >N
    m = re.search(r'\s+([<>]\s*\d+(?:[.,]\d+)?)\s*$', rest)
    if m:
        ref_range = m.group(1).strip()
        unit = rest[:m.start()].strip() or None
        return unit, ref_range

    # Style 3 (CentroSalud): pure-number tokens then a unit token at end.
    # Work backwards: collect trailing non-numeric token(s) as unit.
    tokens = rest.split()
    unit_tokens: list[str] = []
    for tok in reversed(tokens):
        if re.match(r'^[<>]?[\d.,]+$', tok):
            break
        unit_tokens.insert(0, tok)
    n_unit = len(unit_tokens)
    range_tokens = tokens[: len(tokens) - n_unit]
    nums = [t for t in range_tokens if re.match(r'^[\d.,]+$', t)]

    unit = ' '.join(unit_tokens) or None
    if len(nums) == 2:
        ref_range = f"{nums[0].replace(',', '.')}-{nums[1].replace(',', '.')}"
    elif len(nums) == 1:
        ref_range = nums[0]
    else:
        ref_range = None

    return unit, ref_range


# First standalone number: not directly after a word-char or hyphen.
# Supports leading-dot decimals (.89) and optional < > prefix.
_VALUE_RE = re.compile(r'(?<![\w\-])([<>]?(?:\d+(?:[.,]\d+)?|\.\d+))')


def _parse_line(line: str) -> dict | None:
    # Strip markdown bold markers (CentroSalud)
    line = re.sub(r'\*\*', '', line).strip()

    if len(line) < 4:
        return None
    # Skip continuation fragments (lines starting with non-letter or partial-word artefacts)
    if re.match(r'^\s*[()>]', line):
        return None
    if re.match(r'^(?:C\.S\.|EPI\))', line, re.IGNORECASE):
        return None
    if re.match(r'^N.\s*Anal', line) and ':' in line[:15]:
        return None
    if _SKIP_RE.match(line) or _SKIP_CONTAINS_RE.search(line):
        return None

    # Strip trailing validator codes (Adeslas) and lone asterisks
    line = re.sub(r'\s+(?:AUTO|MML)\s*$', '', line)
    line = re.sub(r'\s*\*\s*$', '', line).rstrip()

    m = _VALUE_RE.search(line)
    if not m:
        return None

    name = line[:m.start()].strip().rstrip('(*').strip()
    if not name:
        return None

    val_str = m.group(1).replace(',', '.').lstrip('<>')
    try:
        value = float(val_str)
    except ValueError:
        return None

    unit, ref_range = _extract_unit_and_range(line[m.end():])
    if unit:
        unit = re.sub(r'\s*Intervalo de Referencia.*$', '', unit, flags=re.IGNORECASE).strip() or None
    return {'name': name, 'value': value, 'unit': unit, 'ref_range': ref_range}


def _parse_text(text: str) -> list[dict]:
    params = []
    seen: set[str] = set()
    for line in text.splitlines():
        p = _parse_line(line)
        if p and p['name'] not in seen:
            seen.add(p['name'])
            params.append(p)
    return params


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(pdf_path: str | Path) -> dict:
    """Extract date and parameters from a lab PDF.

    Returns {"date": "YYYY-MM-DD", "parameters": [...]}.
    Raises ValueError if no date can be found.
    """
    pdf_path = Path(pdf_path)
    full_text = ''
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text += (page.extract_text() or '') + '\n'

    date = _date_from_filename(pdf_path) or _date_from_text(full_text)
    if not date:
        raise ValueError(f"Could not find a date in {pdf_path.name}")

    return {'date': date, 'parameters': _parse_text(full_text)}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python extractor.py <file.pdf>')
        sys.exit(1)
    result = extract(sys.argv[1])
    print(f"Date: {result['date']}")
    print(f"Parameters found: {len(result['parameters'])}")
    for p in result['parameters']:
        print(f"  {p['name']}: {p['value']} {p['unit'] or ''} (ref: {p['ref_range'] or '-'})")
