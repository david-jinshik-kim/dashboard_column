import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

st.set_page_config(layout="wide", page_title="Column Element Forces Dashboard")

# Define the file name globally so both the function and the error handler can access it
excel_file = "260306_V9_11(v2)_STR-W -- Element Forces.xlsx"

# --- STEP 1: LOAD AND MERGE DATA FROM EXCEL ---
@st.cache_data
def load_data():
    # Helper to read ETABS Excel sheets
    def read_etabs_sheet(filepath, sheet_name):
        df = pd.read_excel(filepath, sheet_name=sheet_name, skiprows=[0])
        df = df.drop(index=0).reset_index(drop=True)
        return df

    # Load all required sheets
    df_forces = read_etabs_sheet(excel_file, "Element Forces - Columns")
    df_conn = read_etabs_sheet(excel_file, "Column Object Connectivity")
    df_pts = read_etabs_sheet(excel_file, "Point Object Connectivity")
    df_frame = read_etabs_sheet(excel_file, "Frame Assigns - Summary")
    df_groups = read_etabs_sheet(excel_file, "Group Assignments")

    # Convert numeric columns in forces
    num_cols = ['P', 'T', 'V2', 'V3', 'M2', 'M3']
    for col in num_cols:
        df_forces[col] = pd.to_numeric(df_forces[col], errors='coerce')

    # Merge Connectivity
    df_conn = df_conn[['Unique Name', 'Length', 'UniquePtI', 'UniquePtJ']]
    master_df = pd.merge(df_forces, df_conn, on='Unique Name', how='left')

    # Merge Point Coordinates
    df_pts_clean = df_pts[['UniqueName', 'X', 'Y', 'Z']].rename(columns={'UniqueName': 'PointId'})
    master_df = pd.merge(master_df, df_pts_clean.rename(columns={'PointId': 'UniquePtI', 'X': 'Xi', 'Y': 'Yi', 'Z': 'Zi'}), 
                         on='UniquePtI', how='left')
    master_df = pd.merge(master_df, df_pts_clean.rename(columns={'PointId': 'UniquePtJ', 'X': 'Xj', 'Y': 'Yj', 'Z': 'Zj'}), 
                         on='UniquePtJ', how='left')

    # Merge Frame Assigns
    df_frame = df_frame[['UniqueName', 'Analysis Section']].rename(columns={'UniqueName': 'Unique Name'})
    master_df = pd.merge(master_df, df_frame, on='Unique Name', how='left')

    # Merge Group Assignments
    df_groups_clean = df_groups[['Object Unique Name', 'Group Name']].rename(columns={'Object Unique Name': 'Unique Name'})
    group_map = df_groups_clean.groupby('Unique Name')['Group Name'].apply(lambda x: ', '.join(x)).reset_index()
    master_df = pd.merge(master_df, group_map, on='Unique Name', how='left')
    master_df['Group Name'] = master_df['Group Name'].fillna('None')

    cols_to_keep = [
        'Group Name', 'Story', 'Unique Name', 'Output Case', 'P', 'T', 'V2', 'V3', 'M2', 'M3', 
        'Length', 'UniquePtI', 'UniquePtJ', 'Xi', 'Yi', 'Zi', 'Xj', 'Yj', 'Zj', 'Analysis Section'
    ]
    return master_df[cols_to_keep]

try:
    df = load_data()
except Exception as e:
    st.error(f"Error loading the Excel file. Ensure `{excel_file}` is in the same folder as this script. Error: {e}")
    st.stop()


# --- STEP 2: DASHBOARD SLICERS (SIDEBAR) ---
st.sidebar.header("Dashboard Filters")

# Groups Slicer
all_groups_list = sorted(list(set(g for g_str in df['Group Name'].dropna() for g in g_str.split(', '))))
if st.sidebar.checkbox("Select All Group Names", value=True):
    selected_groups = all_groups_list
else:
    selected_groups = st.sidebar.multiselect("Select Group Name(s):", options=all_groups_list, default=all_groups_list[:1])

# Stories Slicer
stories_list = sorted(df['Story'].dropna().unique().tolist())
if st.sidebar.checkbox("Select All Stories", value=True):
    selected_stories = stories_list
else:
    selected_stories = st.sidebar.multiselect("Select Story(ies):", options=stories_list, default=stories_list)

# Output Cases Slicer
cases_list = sorted(df['Output Case'].dropna().unique().tolist())
if st.sidebar.checkbox("Select All Output Cases", value=True):
    selected_cases = cases_list
else:
    selected_cases = st.sidebar.multiselect("Select Output Case(s):", options=cases_list, default=cases_list[:5])

# Apply Filters
def filter_groups(row_group_str, selected_groups):
    if pd.isna(row_group_str): return False
    row_groups = row_group_str.split(', ')
    return any(g in selected_groups for g in row_groups)

mask = (
    df['Group Name'].apply(lambda x: filter_groups(x, selected_groups)) &
    df['Story'].isin(selected_stories) &
    df['Output Case'].isin(selected_cases)
)
filtered_df = df[mask].copy()

if filtered_df.empty:
    st.warning("No data matches the current filter selections. Please adjust your slicers.")
    st.stop()


# --- STEP 3: VISUALIZATIONS ---
st.title("Column Element Forces Dashboard")
st.markdown("---")

# Configuration for element forces and their computation logic
force_configs = [
    {"label": "P(T) [Max Axial Tension]", "col": "P", "metric": "max_pos"},
    {"label": "P(C) [Max Axial Compression]", "col": "P", "metric": "min_neg"},
    {"label": "T [Absolute Max]", "col": "T", "metric": "abs_max"},
    {"label": "V2 [Absolute Max]", "col": "V2", "metric": "abs_max"},
    {"label": "V3 [Absolute Max]", "col": "V3", "metric": "abs_max"},
    {"label": "M2 [Absolute Max]", "col": "M2", "metric": "abs_max"},
    {"label": "M3 [Absolute Max]", "col": "M3", "metric": "abs_max"}
]

# Helper to extract numeric values for Story sorting
def get_story_num(story_str):
    s = str(story_str).upper()
    if s == 'BASE': return 0
    m = re.search(r'\d+', s)
    if m: return int(m.group())
    return -1

# Helper to format Story label (Removing 'F')
def format_story_label(story_str):
    s = str(story_str)
    if s.upper() == 'BASE': return 'Base'
    return s.replace('F', '').replace('f', '')

# Calculate aggregated metrics per story based on new rules
summary_data = []
for story, group in filtered_df.groupby('Story'):
    story_stats = {
        "Story": story,
        "Story_Num": get_story_num(story),
        "Story_Label": format_story_label(story)
    }
    for cfg in force_configs:
        col = cfg['col']
        label = cfg['label']
        
        if cfg['metric'] == "max_pos":
            pos_vals = group.loc[group[col] > 0, col]
            story_stats[label] = pos_vals.max() if not pos_vals.empty else None
        elif cfg['metric'] == "min_neg":
            neg_vals = group.loc[group[col] < 0, col]
            story_stats[label] = neg_vals.min() if not neg_vals.empty else None
        elif cfg['metric'] == "abs_max":
            story_stats[label] = group[col].abs().max()
            
    summary_data.append(story_stats)

df_summary = pd.DataFrame(summary_data)
# Sort by the purely numeric story value
df_summary = df_summary.sort_values(by="Story_Num")

st.subheader("Element Forces - Bar and Box-and-Whisker Plots")

for cfg in force_configs:
    col_str = cfg['label']
    st.markdown(f"### {col_str}")
    
    # Filter out None values for this specific force before plotting
    plot_df = df_summary.dropna(subset=[col_str]).copy()
    
    # Define title strings with HTML for specific font sizing
    main_title_style = "font-size: 24px; font-weight: bold;"
    sub_title_style = "font-size: 16px;"

    if not plot_df.empty:
        overall_max = plot_df[col_str].max()
        overall_min = plot_df[col_str].min()
        
        bar_title = f"<span style='{main_title_style}'>Bar Chart: {col_str} per Story</span><br><span style='{sub_title_style}'>Overall Max: {overall_max:,.2f} | Overall Min: {overall_min:,.2f}</span>"
        box_title = f"<span style='{main_title_style}'>Box Plot: Computed Values for {col_str}</span><br><span style='{sub_title_style}'>Overall Max: {overall_max:,.2f} | Overall Min: {overall_min:,.2f}</span>"
    else:
        bar_title = f"<span style='{main_title_style}'>Bar Chart: {col_str} per Story</span><br><span style='{sub_title_style}'>Overall Max: N/A | Overall Min: N/A</span>"
        box_title = f"<span style='{main_title_style}'>Box Plot: Computed Values for {col_str}</span><br><span style='{sub_title_style}'>Overall Max: N/A | Overall Min: N/A</span>"
    
    # Custom axes configuration
    col_config1, col_config2, col_config3 = st.columns([1, 1, 1])
    with col_config1:
        use_custom = st.checkbox("Custom X-axis Bounds", key=f"check_{col_str}")
    with col_config2:
        x_min = st.number_input("Min X", value=-1000.0, disabled=not use_custom, key=f"min_{col_str}")
    with col_config3:
        x_max = st.number_input("Max X", value=1000.0, disabled=not use_custom, key=f"max_{col_str}")
    
    # Render Bar Chart First (Top)
    fig_bar = px.bar(
        plot_df, 
        x=col_str, 
        y="Story_Label", 
        orientation='h', 
        color=col_str,
        color_continuous_scale="Viridis"
    )
    
    # Apply dynamically styled title
    fig_bar.update_layout(title_text=bar_title, title_x=0.0)
    
    # Force the Y-axis to respect the sorted order of the dataframe
    fig_bar.update_yaxes(categoryorder='array', categoryarray=plot_df['Story_Label'].tolist())
    
    if use_custom: 
        fig_bar.update_xaxes(range=[x_min, x_max])
    st.plotly_chart(fig_bar, use_container_width=True)

    # Render Box Plot Second (Bottom)
    box_df = plot_df.copy()
    box_df['Element Force'] = col_str  # Y-Axis Mapping
    
    fig_box = px.box(
        box_df, 
        x=col_str, 
        y='Element Force', 
        orientation='h', 
        points="all" # Display all data points over the box plot
    )
    
    # Apply dynamically styled title
    fig_box.update_layout(title_text=box_title, title_x=0.0)
    
    # Center the points directly over the box using pointpos=0, and add slight jitter 
    fig_box.update_traces(pointpos=0, jitter=0.2)
    
    if use_custom: 
        fig_box.update_xaxes(range=[x_min, x_max])
    st.plotly_chart(fig_box, use_container_width=True)
    st.markdown("---")


# --- STEP 4: TABLES ---
st.header("Data Tables")

# Table 1: Global maximums (Mapped to the exact rows calculating those maximums)
st.subheader("Global Maximum Element Forces (Based on Selection)")
max_rows = []

for cfg in force_configs:
    target_col = cfg['col']
    idx = None
    
    if cfg['metric'] == 'max_pos':
        sub_df = filtered_df[filtered_df[target_col] > 0]
        if not sub_df.empty: idx = sub_df[target_col].idxmax()
            
    elif cfg['metric'] == 'min_neg':
        sub_df = filtered_df[filtered_df[target_col] < 0]
        if not sub_df.empty: idx = sub_df[target_col].idxmin()
            
    elif cfg['metric'] == 'abs_max':
        if not filtered_df.empty:
            idx = filtered_df[target_col].abs().idxmax()
    
    if idx is not None and pd.notna(idx):
        row_data = filtered_df.loc[idx].to_dict()
        row_data['Maximum Type'] = cfg['label']
        max_rows.append(row_data)

if max_rows:
    df_max_table = pd.DataFrame(max_rows)
    # Move "Maximum Type" to the front
    cols = ['Maximum Type'] + [c for c in df_max_table.columns if c != 'Maximum Type']
    st.dataframe(df_max_table[cols], use_container_width=True)
else:
    st.info("No matching max rows to display for the current selection.")

# Table 2: All filtered rows, specific column ordering
st.subheader("Filtered Element Forces Data")
st.write(f"**Total Rows:** {len(filtered_df)}")

# Reorder base attributes and element forces specifically
ordered_cols = [
    'Story', 'Unique Name', 'Group Name', 'Output Case', 
    'P', 'T', 'V2', 'M3', 'V3', 'M2', 
    'Length', 'UniquePtI', 'UniquePtJ', 'Xi', 'Yi', 'Zi', 'Xj', 'Yj', 'Zj', 'Analysis Section'
]
df_table_2 = filtered_df[ordered_cols]
st.dataframe(df_table_2, use_container_width=True)