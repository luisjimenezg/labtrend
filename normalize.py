"""
Parameter name normalization: maps raw extracted names (with encoding
artefacts and lab-specific naming variations) to canonical names.

normalize_name(raw) returns:
  - a canonical string if the name is a known parameter
  - None if the name should be discarded (metadata / noise)
  - raw unchanged if no mapping found (unknown parameter, keep as-is)
"""
import re

# ---------------------------------------------------------------------------
# Pre-processing
# ---------------------------------------------------------------------------

def _prep(name: str) -> str:
    """Fix encoding artefacts before matching."""
    # Null byte = 'ti' ligature in some PDF encodings
    name = name.replace('\x00', 'ti')
    return name.strip()


# ---------------------------------------------------------------------------
# Discard patterns (metadata / noise that slipped past extraction filters)
# ---------------------------------------------------------------------------

_DISCARD_RE = re.compile(
    r'^\+$'                                          # lone "+"
    r'|^Av\.'                                        # street address
    r'|^(?:Cobertura|Servicio|Sociedad)\s*:'         # admin headers
    r'|^N[º°]\s*(?:Colegiado|Laboratorio|Cobertura)' # doctor/lab IDs
    r'|^www\.'                                       # URLs
    r'|^Tras\s+ayuno'                                # fasting note
    r'|^Modificaci'                                  # reference-range change note
    r'|^Positivo:|^Embarazo:|^moderado:|^Indeterminado$'  # range labels
    r'|^realiza\s+durante'                           # Spanish prose
    r'|^(?:reports|the first week|tiene un)\b'       # English prose / noise
    r'|^TTPA \(Plasma Enf\.'                         # CentroSalud continuation
    r'|^Filtrado Glomerular estimado \(CKD-$'        # CentroSalud truncated line
    r'|^Capacidad total de saturaci',                # truncated line
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Normalization rules: (pattern, canonical_name)
# Applied in order; first match wins.
# Patterns use re.IGNORECASE by default.
# ---------------------------------------------------------------------------

_RULES: list[tuple[str, str]] = [

    # ── Erythrocytes ─────────────────────────────────────────────────────
    (r'^Hemat.es$|^Eritrocitos$',               'Hematíes'),
    (r'^Volumen [Cc]orpuscular [Mm]edio(?: sangre)?$|^VCM$',
                                                 'VCM'),
    (r'^Hemoglobina [Cc]orpuscular [Mm]edia$|^HCM$',
                                                 'HCM'),
    (r'^Conc\. Hemoglobina Corpuscular$|^CHCM$', 'CHCM'),
    (r'^Coeficiente de anisocitosis$|^RDW$|^ADE$', 'RDW'),
    (r'^(?:Recuento de )?[Pp]laquetas$',         'Plaquetas'),
    (r'^Volumen plaquetar medio$|^VPM$',          'Volumen plaquetar medio'),

    # ── Leukocyte differential (absolute) ────────────────────────────────
    (r'^Linfocitos(?: \(ABS\))?$',               'Linfocitos'),
    (r'^Monocitos(?: \(ABS\))?$',                'Monocitos'),
    (r'^(?:Segmentados \(ABS\)|Neutr.filos)$',   'Neutrófilos'),
    (r'^Eosin.filos(?: \(ABS\))?$',              'Eosinófilos'),
    (r'^Bas.filos(?: \(ABS\))?$',                'Basófilos'),

    # ── Leukocyte differential (%) ────────────────────────────────────────
    (r'^%\s*linfocitos$|^Linfocitos %$|^Linfocitos \(%\)$',
                                                 'Linfocitos %'),
    (r'^%\s*monocitos$|^Monocitos %$|^Monocitos \(%\)$',
                                                 'Monocitos %'),
    (r'^%\s*segmentados$|^Neutr.filos %$|^Neutr.filos \(%\)$',
                                                 'Neutrófilos %'),
    (r'^%\s*eosin.filos$|^Eosin.filos %$|^Eosin.filos \(%\)$',
                                                 'Eosinófilos %'),
    (r'^%\s*bas.filos$|^Bas.filos %$|^Bas.filos \(%\)$',
                                                 'Basófilos %'),

    # ── Basic biochemistry ───────────────────────────────────────────────
    (r'^Crea.nina$',                             'Creatinina'),
    (r'^Creatinina \(mg/dl\)$',                  'Creatinina orina'),
    (r'^Bilirrubina [Tt]otal$',                  'Bilirrubina total'),
    (r'^F.sforo$|^Fosforo$',                     'Fósforo'),
    (r'^.cido .rico$|^Acido .rico$|^Ac\. Urico$', 'Ácido úrico'),

    # ── Enzymes ─────────────────────────────────────────────────────────
    (r'^ASAT \(GOT\)$|^GOT \(AST\)$',           'GOT/AST'),
    (r'^ALAT \(GPT\)$|^GPT \(ALT\)$',           'GPT/ALT'),
    (r'^Fosfatasa [Aa]lcalina$',                 'Fosfatasa alcalina'),

    # ── Lipids ───────────────────────────────────────────────────────────
    (r'^Colesterol [Tt]otal$',                   'Colesterol total'),
    (r'^Colesterol.?HDL$',                       'Colesterol HDL'),
    (r'^Colesterol LDL(?: \(Calculado\))?$',     'Colesterol LDL'),
    (r'^Triglic.ridos$|^Trigliceridos$',         'Triglicéridos'),

    # ── Proteins ─────────────────────────────────────────────────────────
    (r'^Prote.nas totales$|^Proteinas Totales$', 'Proteínas totales'),
    (r'^Prote.na C rea.?\w*$|^Proteina C Reactiva$|^Proteina C-reactiva.*',
                                                 'Proteína C reactiva'),

    # ── Thyroid ──────────────────────────────────────────────────────────
    (r'^T\.S\.H\.$|^TSH$',                       'TSH'),

    # ── Coagulation ──────────────────────────────────────────────────────
    (r'^I\.N\.R\.$|^INR$',                        'INR'),
    (r'^[Tt]iempo de [Pp]rotrombina$',            'Tiempo de protrombina'),
    (r'^Indice de Quick$|^Actividad de Protrombina$|^Actividad de protrombina.*',
                                                  'Índice de Quick'),
    (r'^TTPA$|^TTP Ra.{1,2}o$|^Tiempo de Cefalina.*|^Control TTPA$',
                                                  'TTPA'),
    (r'^Fibrin.geno$',                            'Fibrinógeno'),
    (r'^Fibrin.geno derivado$',                   'Fibrinógeno derivado'),

    # ── Iron panel ───────────────────────────────────────────────────────
    (r'^Ferri.{1,2}na$',                          'Ferritina'),
    (r'^.ndice (?:de )?Saturaci.n (?:de )?Transferrina$|^Indice Saturaci.n Transferrina$',
                                                  'Saturación transferrina'),

    # ── Renal ────────────────────────────────────────────────────────────
    (r'^Filtrado glomerular es.{1,2}mado \(CKD.EPI\)$|^Filtrado Glomerular estimado$',
                                                  'FGe CKD-EPI'),
    (r'^Filtrado Glomerular estimado \(CKD-$',    None),  # truncated → discard
    (r'^Filtrado glomerular estimado \(MDRD4?\)$', 'FGe MDRD4'),
    (r'^Alb.mina/Creatinina \(una$|^Alb.mina/Creatinina \(una mic',
                                                  'Alb/Creatinina orina'),

    # ── HbA1c ────────────────────────────────────────────────────────────
    (r'^HbA1c \(Glicohemoglobina\)$',             'HbA1c (%)'),

    # ── pH / urinary vs blood ─────────────────────────────────────────────
    # "Ph" alone comes from the urinary analysis section in HM Hospital PDFs
    (r'^Ph$',                                     'pH orina'),
    (r'^pH$|^Ph, gasometr.a.*',                   'pH'),

    # ── Gasometry ────────────────────────────────────────────────────────
    (r'^PCO2, gasometr.a$|^pCO2$',               'pCO2'),
    (r'^PO2, gasometr.a$|^pO2$',                 'pO2'),
    (r'^Bicarbonato actual, gasometr.a$|^HCO3-$', 'HCO3-'),
    (r'^CO2 total, gasometr.a$',                  'CO2 total'),
    (r'^Ani.n Gap calculado$',                    'Anión Gap'),
]

# Compile once
_COMPILED: list[tuple[re.Pattern, str | None]] = [
    (re.compile(pat, re.IGNORECASE), canon)
    for pat, canon in _RULES
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_name(raw: str) -> str | None:
    """Return the canonical parameter name, or None to discard the entry."""
    name = _prep(raw)

    if not name or _DISCARD_RE.match(name):
        return None

    for pattern, canonical in _COMPILED:
        if pattern.match(name):
            return canonical  # may be None (explicit discard rule)

    return name  # no mapping → keep as-is
