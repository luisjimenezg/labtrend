import streamlit as st
import plotly.express as px
import pandas as pd

import database as db
from extractor import extract

st.set_page_config(page_title="Lab Trend", page_icon="🧪", layout="wide")
db.init_db()

st.title("Lab Trend")

# ── Sidebar: import new PDF ───────────────────────────────────────────────
with st.sidebar:
    st.header("Import PDF")
    uploaded = st.file_uploader("Select a lab PDF", type="pdf")

    if uploaded:
        import tempfile, pathlib
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = pathlib.Path(tmp.name)

        try:
            result = extract(tmp_path)
            st.info(f"Date detected: **{result['date']}**  \n{len(result['parameters'])} parameters found")

            if st.button("Import into database"):
                try:
                    db.insert_analysis(result["date"], uploaded.name, result["parameters"])
                    st.success("Imported successfully.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        except ValueError as e:
            st.error(str(e))
        finally:
            tmp_path.unlink(missing_ok=True)

    st.divider()

    # List imported analyses
    st.header("Imported analyses")
    analyses = db.list_analyses()
    if analyses:
        for a in analyses:
            col1, col2 = st.columns([3, 1])
            col1.markdown(f"**{a['date']}**  \n{a['source_file'] or ''}")
            if col2.button("🗑", key=f"del_{a['id']}"):
                db.delete_analysis(a["id"])
                st.rerun()
    else:
        st.caption("No analyses imported yet.")

# ── Main area: parameter chart ────────────────────────────────────────────
names = db.get_parameter_names()

if not names:
    st.info("Import at least one PDF from the sidebar to get started.")
else:
    selected = st.selectbox("Select a parameter", names)

    rows = db.get_series(selected)
    if rows:
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        unit = df["unit"].dropna().iloc[0] if df["unit"].notna().any() else ""

        fig = px.line(
            df,
            x="date",
            y="value",
            markers=True,
            title=f"{selected}" + (f" ({unit})" if unit else ""),
            labels={"date": "Date", "value": unit or "Value"},
        )
        fig.update_traces(line_width=2, marker_size=8)
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Raw data"):
            st.dataframe(df.rename(columns={"date": "Date", "value": "Value", "unit": "Unit"}), hide_index=True)
    else:
        st.warning("No data for this parameter.")
