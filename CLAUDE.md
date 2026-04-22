# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

Personal tool for tracking clinical lab results over time for a single patient. PDFs are parsed to extract dates and parameters, stored in a local SQLite database, and visualized as time-series charts in a Streamlit web UI.

## Critical constraints

- **`pdfs/`, `*.pdf`, `data/`, `*.db`, `*.json` are gitignored and must never be committed** — they contain sensitive patient data.
- GitHub remote: personal account `luisjimenezg` / `luisjimenezg@gmail.com`.

## Running the app

```bash
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Start the UI
streamlit run app.py

# Test PDF extraction before importing (inspect output without touching the DB)
python extractor.py pdfs/some_analysis.pdf
```

## Architecture

Three modules with a clear dependency direction: `app.py` → `database.py` + `extractor.py` (no cross-dependency between the latter two).

| File | Responsibility |
|---|---|
| `extractor.py` | Opens a PDF with `pdfplumber`, extracts full text, then uses regex to find the analysis date and parameter rows (name / value / unit / reference range). Standalone — no DB dependency. |
| `database.py` | All SQLite access. Schema: `analyses` (one row per date) + `parameters` (many rows per analysis). Exposes `init_db`, `insert_analysis`, `get_series`, `get_parameter_names`, `list_analyses`, `delete_analysis`. |
| `app.py` | Streamlit entry point. Sidebar handles PDF upload → extraction preview → DB import and deletion of existing analyses. Main area shows a Plotly time-series chart for the selected parameter. |

Database lives at `data/labtrend.db` (created on first run).

## Tuning the extractor

`extractor.py` uses heuristic regex (`_PARAM_RE`) that may not match every lab report layout. When adding support for a new PDF format:
1. Run `python extractor.py <file.pdf>` and inspect what's captured vs. missed.
2. Adjust `_PARAM_RE` or `_DATE_PATTERNS` in `extractor.py` — keep the patterns general enough to cover all labs already imported.
3. There is no test suite yet; manual inspection via the CLI command is the workflow.
