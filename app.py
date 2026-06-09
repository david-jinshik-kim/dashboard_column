import streamlit as st
from core.data_loader import load_data
from components.sidebar import render_sidebar_filters
from components.visualizations import render_charts
from components.tables_export import render_tables_and_export

# Global configuration for forces (passed to components)
FORCE_CONFIGS = [
    {"label": "P(T) [Max Axial Tension]", "col": "P", "metric": "max_pos"},
    {"label": "P(C) [Max Axial Compression]", "col": "P", "metric": "min_neg"},
    {"label": "T [Absolute Max]", "col": "T", "metric": "abs_max"},
    {"label": "V2 [Absolute Max]", "col": "V2", "metric": "abs_max"},
    {"label": "V3 [Absolute Max]", "col": "V3", "metric": "abs_max"},
    {"label": "M2 [Absolute Max]", "col": "M2", "metric": "abs_max"},
    {"label": "M3 [Absolute Max]", "col": "M3", "metric": "abs_max"}
]

st.set_page_config(layout="wide", page_title="Column Element Forces Dashboard")
st.title("Column Element Forces Dashboard")

# --- FILE UPLOAD ---
st.sidebar.header("Data Source")
uploaded_file = st.sidebar.file_uploader("Upload ETABS Excel File", type=["xlsx", "xls"])

if not uploaded_file:
    st.info("👋 Please upload your ETABS Element Forces Excel file using the sidebar to generate the dashboard.")
    st.stop()

# --- LOAD DATA ---
try:
    df = load_data(uploaded_file)
except Exception as e:
    st.error(f"Error processing the Excel file. Details: {e}")
    st.stop()

# --- SIDEBAR FILTERS ---
filtered_df = render_sidebar_filters(df)

if filtered_df.empty:
    st.warning("No data matches the current filter selections.")
    st.stop()

# --- RENDER COMPONENTS ---
render_charts(filtered_df, FORCE_CONFIGS)
render_tables_and_export(filtered_df, FORCE_CONFIGS)