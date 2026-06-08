import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- 1. DATA LOADING AND CLEANING ---
@st.cache_data # Caches the data so it doesn't reload on every dropdown change
def load_data():
    excel_file = '260306_V9_11(v2)_STR-W -- Element Forces.xlsx'
    
    # Read directly from the Excel sheets. 
    # ETABS usually has the table name on row 0, headers on row 1, and units on row 2.
    # header=1 sets row 2 as headers, and .iloc[1:] skips the units row.
    df_forces = pd.read_excel(excel_file, sheet_name='Element Forces - Columns', header=1).iloc[1:]
    df_conn = pd.read_excel(excel_file, sheet_name='Column Object Connectivity', header=1).iloc[1:]
    df_pts = pd.read_excel(excel_file, sheet_name='Point Object Connectivity', header=1).iloc[1:]
    df_frame = pd.read_excel(excel_file, sheet_name='Frame Assigns - Summary', header=1).iloc[1:]
    df_groups = pd.read_excel(excel_file, sheet_name='Group Assignments', header=1).iloc[1:]

    # Rename columns in Point table for easier merging
    df_pts = df_pts.rename(columns={'UniqueName': 'UniquePt', 'X': 'X', 'Y': 'Y', 'Z': 'Z'})
    
    # Rename columns in Frame Assigns and Group Assignments to match the merge key
    if 'UniqueName' in df_frame.columns:
        df_frame = df_frame.rename(columns={'UniqueName': 'Unique Name'})
    df_groups = df_groups.rename(columns={'Object Unique Name': 'Unique Name'})

    # Merge Forces with Connectivity
    df = pd.merge(df_forces, df_conn[['Unique Name', 'Length', 'UniquePtI', 'UniquePtJ']], on='Unique Name', how='left')

    # Merge Point I coordinates
    df = pd.merge(df, df_pts[['UniquePt', 'X', 'Y', 'Z']], left_on='UniquePtI', right_on='UniquePt', how='left')
    df = df.rename(columns={'X': 'Xi', 'Y': 'Yi', 'Z': 'Zi'}).drop(columns=['UniquePt'])

    # Merge Point J coordinates
    df = pd.merge(df, df_pts[['UniquePt', 'X', 'Y', 'Z']], left_on='UniquePtJ', right_on='UniquePt', how='left')
    df = df.rename(columns={'X': 'Xj', 'Y': 'Yj', 'Z': 'Zj'}).drop(columns=['UniquePt'])

    # Merge Frame Assigns (Analysis Section)
    df = pd.merge(df, df_frame[['Unique Name', 'Analysis Section']], on='Unique Name', how='left')
    
    # Merge Group Assignments
    df = pd.merge(df, df_groups[['Unique Name', 'Group Name']], on='Unique Name', how='left')

    # Convert numeric columns from string/object to float
    num_cols = ['P', 'T', 'V2', 'V3', 'M2', 'M3', 'Xi', 'Yi', 'Zi', 'Xj', 'Yj', 'Zj', 'Length']
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    return df

# Load the data
df = load_data()

# --- 2. DASHBOARD FILTERS ---
st.title("Column Element Forces 3D Dashboard")
st.sidebar.header("Filters")

# Extract unique values for drop-down lists
stories = ["All"] + list(df['Story'].dropna().unique())
output_cases = ["All"] + list(df['Output Case'].dropna().unique())
groups = ["All"] + list(df['Group Name'].dropna().unique())
force_options = ['P', 'T', 'V2', 'V3', 'M2', 'M3']

# Create Dropdowns
selected_story = st.sidebar.selectbox("Select Story", stories)
selected_case = st.sidebar.selectbox("Select Output Case", output_cases)
selected_group = st.sidebar.selectbox("Select Group Name", groups)
selected_force = st.sidebar.selectbox("Select Force to Visualize", force_options)

# Filter the dataframe based on selections
filtered_df = df.copy()
if selected_story != "All":
    filtered_df = filtered_df[filtered_df['Story'] == selected_story]
if selected_case != "All":
    filtered_df = filtered_df[filtered_df['Output Case'] == selected_case]
if selected_group != "All":
    filtered_df = filtered_df[filtered_df['Group Name'] == selected_group]

# Drop duplicates if multiple stations exist per column
# We keep the row with the maximum absolute force for visualization purposes
filtered_df['Abs_Force'] = filtered_df[selected_force].abs()
viz_df = filtered_df.loc[filtered_df.groupby('Unique Name')['Abs_Force'].idxmax()]

# --- 3. 3D VISUALIZATION ---
st.subheader(f"3D Model - Visualizing {selected_force}")

if viz_df.empty:
    st.warning("No data matches the selected filters.")
else:
    fig = go.Figure()

    # Determine color scale bounds based on actual (non-absolute) forces
    min_force = viz_df[selected_force].min()
    max_force = viz_df[selected_force].max()

    # Create coordinate arrays (separated by None) for fast rendering
    x_lines = []
    y_lines = []
    z_lines = []
    hover_texts = []

    for _, row in viz_df.iterrows():
        # Coordinates
        x_lines.extend([row['Xi'], row['Xj'], None])
        y_lines.extend([row['Yi'], row['Yj'], None])
        z_lines.extend([row['Zi'], row['Zj'], None])
        
        # Hover info
        text = f"Name: {row['Unique Name']}<br>Story: {row['Story']}<br>Section: {row['Analysis Section']}<br>{selected_force}: {row[selected_force]:.2f}"
        hover_texts.extend([text, text, None])

    # Add the lines to the figure
    fig.add_trace(go.Scatter3d(
        x=x_lines,
        y=y_lines,
        z=z_lines,
        mode='lines',
        line=dict(
            color=viz_df[selected_force].repeat(3).reset_index(drop=True), 
            colorscale='Viridis',
            width=5,
            cmin=min_force,
            cmax=max_force,
            colorbar=dict(title=f"{selected_force} Magnitude")
        ),
        hoverinfo='text',
        hovertext=hover_texts
    ))

    # Formatting the layout
    fig.update_layout(
        scene=dict(
            xaxis_title='X (m)',
            yaxis_title='Y (m)',
            zaxis_title='Z (m)',
            aspectmode='data' # Keeps architectural proportions 1:1:1
        ),
        height=700,
        margin=dict(r=10, l=10, b=10, t=10)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Show the raw merged data table below the chart
    st.subheader("Filtered Data Table")
    st.dataframe(viz_df[['Unique Name', 'Story', 'Group Name', 'Output Case', 'Analysis Section', selected_force, 'Length']])