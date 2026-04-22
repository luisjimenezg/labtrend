import sqlite3
from pathlib import Path

DB_PATH = Path("data/labtrend.db")


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS analyses (
                id          INTEGER PRIMARY KEY,
                date        TEXT NOT NULL UNIQUE,
                source_file TEXT
            );

            CREATE TABLE IF NOT EXISTS parameters (
                id           INTEGER PRIMARY KEY,
                analysis_id  INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                name         TEXT NOT NULL,
                value        REAL,
                unit         TEXT,
                ref_range    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_parameters_name ON parameters(name);
        """)


def insert_analysis(date: str, source_file: str, parameters: list[dict]) -> int:
    """Insert an analysis and its parameters. Returns the analysis id.
    parameters: list of {name, value, unit, ref_range}
    Raises ValueError if the date already exists.
    """
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO analyses (date, source_file) VALUES (?, ?)",
                (date, source_file),
            )
            analysis_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"An analysis for date {date} already exists.")

        conn.executemany(
            "INSERT INTO parameters (analysis_id, name, value, unit, ref_range) VALUES (?, ?, ?, ?, ?)",
            [(analysis_id, p["name"], p.get("value"), p.get("unit"), p.get("ref_range")) for p in parameters],
        )
        return analysis_id


def get_parameter_names() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT name FROM parameters ORDER BY name"
        ).fetchall()
    return [r["name"] for r in rows]


def get_series(parameter_name: str) -> list[dict]:
    """Return [{date, value, unit}] sorted by date for a given parameter."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.date, p.value, p.unit
            FROM parameters p
            JOIN analyses a ON a.id = p.analysis_id
            WHERE p.name = ?
            ORDER BY a.date
            """,
            (parameter_name,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_analyses() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, date, source_file FROM analyses ORDER BY date"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_analysis(analysis_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
