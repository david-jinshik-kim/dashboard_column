import streamlit as st
import os
from core.data_loader import load_data
from components.sidebar import render_sidebar_filters
from components.visualizations import render_charts
from components.tables_export import render_tables_and_export

# Global configuration for forces
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

# --- 1. DUAL FILE UPLOAD & PRELOADED DATA ---
st.sidebar.header("Data Source")
uploaded_file = st.sidebar.file_uploader("Upload ETABS Data", type=["xlsx", "xls"])

query_params = st.query_params
url_dataset = query_params.get("dataset") 
DATA_FOLDER = "datasets" 

data_source = None

if uploaded_file is not None:
    data_source = uploaded_file
    st.sidebar.success(f"✅ Using uploaded file: {uploaded_file.name}")
elif url_dataset:
    # Check for both .xlsx and .xls extensions in the datasets folder
    if os.path.exists(f"{DATA_FOLDER}/{url_dataset}.xlsx"):
        data_source = f"{DATA_FOLDER}/{url_dataset}.xlsx"
        st.sidebar.info(f"ℹ️ Using preloaded dataset: **{url_dataset}.xlsx**")
    elif os.path.exists(f"{DATA_FOLDER}/{url_dataset}.xls"):
        data_source = f"{DATA_FOLDER}/{url_dataset}.xls"
        st.sidebar.info(f"ℹ️ Using preloaded dataset: **{url_dataset}.xls**")
    else:
        st.sidebar.error(f"❌ Preloaded dataset '{url_dataset}' not found in the {DATA_FOLDER} folder.")

if data_source is None:
    st.info("👋 Please upload your ETABS Element Forces file using the sidebar, or use a valid project link.")
    st.stop()

# --- 2. LOAD DATA ---
try:
    df = load_data(data_source)
except Exception as e:
    st.error(f"Error processing the Excel file. Details: {e}")
    st.stop()

# --- 3. SIDEBAR FILTERS ---
filtered_df = render_sidebar_filters(df)

if filtered_df.empty:
    st.warning("No data matches the current filter selections.")
    st.stop()

# --- 4. RENDER COMPONENTS ---
render_charts(filtered_df, FORCE_CONFIGS)
render_tables_and_export(filtered_df, FORCE_CONFIGS)
