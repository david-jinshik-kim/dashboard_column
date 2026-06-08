import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

st.set_page_config(layout="wide", page_title="Column Element Forces Dashboard")

st.title("Column Element Forces Dashboard")

# --- STEP 1: FILE UPLOAD ---
st.sidebar.header("Data Source")
uploaded_file = st.sidebar.file_uploader("Upload ETABS Excel File", type=["xlsx", "xls"])

if not uploaded_file:
    st.info("👋 Please upload your ETABS Element Forces Excel file using the sidebar to generate the dashboard.")
    st.stop()

# --- STEP 2: LOAD AND MERGE DATA FROM EXCEL ---
@st.cache_data
def load_data(file_buffer):
    xls = pd.ExcelFile(file_buffer)
    
    def read_etabs_sheet(excel_obj, sheet_name):
        df = pd.read_excel(excel_obj, sheet_name=sheet_name, skiprows=[0])
        df = df.drop(index=0).reset_index(drop=True)
        return df

    df_forces = read_etabs_sheet(xls, "Element Forces - Columns")
    df_conn = read_etabs_sheet(xls, "Column Object Connectivity")
    df_pts = read_etabs_sheet(xls, "Point Object Connectivity")
    df_frame = read_etabs_sheet(xls, "Frame Assigns - Summary")
    df_groups = read_etabs_sheet(xls, "Group Assignments")

    num_cols = ['P', 'T', 'V2', 'V3', 'M2', 'M3']
    for col in num_cols:
        df_forces[col] = pd.to_numeric(df_forces[col], errors='coerce')

    df_conn = df_conn[['Unique Name', 'Length', 'UniquePtI', 'UniquePtJ']]
    master_df = pd.merge(df_forces, df_conn, on='Unique Name', how='left')

    df_pts_clean = df_pts[['UniqueName', 'X', 'Y', 'Z']].rename(columns={'UniqueName': 'PointId'})
    master_df = pd.merge(master_df, df_pts_clean.rename(columns={'PointId': 'UniquePtI', 'X': 'Xi', 'Y': 'Yi', 'Z': 'Zi'}), 
                         on='UniquePtI', how='left')
    master_df = pd.merge(master_df, df_pts_clean.rename(columns={'PointId': 'UniquePtJ', 'X': 'Xj', 'Y': 'Yj', 'Z': 'Zj'}), 
                         on='UniquePtJ', how='left')

    df_frame = df_frame[['UniqueName', 'Analysis Section']].rename(columns={'UniqueName': 'Unique Name'})
    master_df = pd.merge(master_df, df_frame, on='Unique Name', how='left')

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
    df = load_data(uploaded_file)
except Exception as e:
    st.error(f"Error processing the Excel file. Ensure it has the correct ETABS sheets. Error Details: {e}")
    st.stop()


# --- STEP 3: DASHBOARD SLICERS (SIDEBAR) ---
st.sidebar.markdown("---")
st.sidebar.header("Dashboard Filters")

all_groups_list = sorted(list(set(g for g_str in df['Group Name'].dropna() for g in g_str.split(', '))))
if st.sidebar.checkbox("Select All Group Names", value=True):
    selected_groups = all_groups_list
else:
    selected_groups = st.sidebar.multiselect("Select Group Name(s):", options=all_groups_list, default=all_groups_list[:1])

stories_list = sorted(df['Story'].dropna().unique().tolist())
if st.sidebar.checkbox("Select All Stories", value=True):
    selected_stories = stories_list
else:
    selected_stories = st.sidebar.multiselect("Select Story(ies):", options=stories_list, default=stories_list)

cases_list = sorted(df['Output Case'].dropna().unique().tolist())
if st.sidebar.checkbox("Select All Output Cases", value=True):
    selected_cases = cases_list
else:
    selected_cases = st.sidebar.multiselect("Select Output Case(s):", options=cases_list, default=cases_list[:5])

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


# --- STEP 4: VISUALIZATIONS ---
st.markdown("---")

force_configs = [
    {"label": "P(T) [Max Axial Tension]", "col": "P", "metric": "max_pos"},
    {"label": "P(C) [Max Axial Compression]", "col": "P", "metric": "min_neg"},
    {"label": "T [Absolute Max]", "col": "T", "metric": "abs_max"},
    {"label": "V2 [Absolute Max]", "col": "V2", "metric": "abs_max"},
    {"label": "V3 [Absolute Max]", "col": "V3", "metric": "abs_max"},
    {"label": "M2 [Absolute Max]", "col": "M2", "metric": "abs_max"},
    {"label": "M3 [Absolute Max]", "col": "M3", "metric": "abs_max"}
]

def get_story_num(story_str):
    s = str(story_str).upper()
    if s == 'BASE': return 0
    m = re.search(r'\d+', s)
    if m: return int(m.group())
    return -1

def format_story_label(story_str):
    s = str(story_str)
    if s.upper() == 'BASE': return 'Base'
    return s.replace('F', '').replace('f', '')

# --- NEW: Extract Master Story List for Fixed Bar Chart Axes ---
all_unique_stories = df['Story'].dropna().unique()
master_stories = [{"Story_Num": get_story_num(s), "Story_Label": format_story_label(s)} for s in all_unique_stories]
master_story_labels = pd.DataFrame(master_stories).sort_values("Story_Num")['Story_Label'].tolist()


# Compute Story Aggregations
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

df_summary = pd.DataFrame(summary_data).sort_values(by="Story_Num")

# Compute Individual Element Aggregations (for Colored 3D Plot overlay)
element_summary_data = []
for uname, group in filtered_df.groupby('Unique Name'):
    if pd.isna(group['Xi'].iloc[0]): continue
        
    estats = {
        "Unique Name": uname,
        "Xi": group["Xi"].iloc[0], "Yi": group["Yi"].iloc[0], "Zi": group["Zi"].iloc[0],
        "Xj": group["Xj"].iloc[0], "Yj": group["Yj"].iloc[0], "Zj": group["Zj"].iloc[0],
    }
    for cfg in force_configs:
        col = cfg['col']
        label = cfg['label']
        if cfg['metric'] == "max_pos":
            pos_vals = group.loc[group[col] > 0, col]
            estats[label] = pos_vals.max() if not pos_vals.empty else None
        elif cfg['metric'] == "min_neg":
            neg_vals = group.loc[group[col] < 0, col]
            estats[label] = neg_vals.min() if not neg_vals.empty else None
        elif cfg['metric'] == "abs_max":
            estats[label] = group[col].abs().max()
    element_summary_data.append(estats)

df_elem_summary = pd.DataFrame(element_summary_data)

# Pre-compute coordinates for ALL columns in the structural model (for Gray Background Trace)
bg_x, bg_y, bg_z = [], [], []
for _, group in df.groupby('Unique Name'):
    if pd.notna(group['Xi'].iloc[0]):
        bg_x.extend([group['Xi'].iloc[0], group['Xj'].iloc[0], None])
        bg_y.extend([group['Yi'].iloc[0], group['Yj'].iloc[0], None])
        bg_z.extend([group['Zi'].iloc[0], group['Zj'].iloc[0], None])


st.subheader("Element Forces - 3D Views, Bar Charts, and Box Plots")

for cfg in force_configs:
    col_str = cfg['label']
    st.markdown(f"### {col_str}")
    
    # Check if this is the P(C) force. If so, reverse the color scale.
    c_scale = "Viridis_r" if cfg['metric'] == "min_neg" else "Viridis"
    
    plot_df = df_summary.dropna(subset=[col_str]).copy()
    plot_elem_df = df_elem_summary.dropna(subset=[col_str, 'Xi', 'Xj']).copy()
    
    main_title_style = "font-size: 24px; font-weight: bold;"
    sub_title_style = "font-size: 16px;"

    if not plot_df.empty:
        overall_max = plot_df[col_str].max()
        overall_min = plot_df[col_str].min()
        
        fig3d_title = f"<span style='{main_title_style}'>3D View: {col_str}</span><br><span style='{sub_title_style}'>Overall Max: {overall_max:,.2f} | Overall Min: {overall_min:,.2f}</span>"
        bar_title = f"<span style='{main_title_style}'>Bar Chart: {col_str} per Story</span><br><span style='{sub_title_style}'>Overall Max: {overall_max:,.2f} | Overall Min: {overall_min:,.2f}</span>"
        box_title = f"<span style='{main_title_style}'>Box Plot: Computed Values for {col_str}</span><br><span style='{sub_title_style}'>Overall Max: {overall_max:,.2f} | Overall Min: {overall_min:,.2f}</span>"
    else:
        overall_max, overall_min = 0, 0
        fig3d_title = f"<span style='{main_title_style}'>3D View: {col_str}</span><br><span style='{sub_title_style}'>Overall Max: N/A | Overall Min: N/A</span>"
        bar_title = f"<span style='{main_title_style}'>Bar Chart: {col_str} per Story</span><br><span style='{sub_title_style}'>Overall Max: N/A | Overall Min: N/A</span>"
        box_title = f"<span style='{main_title_style}'>Box Plot: Computed Values for {col_str}</span><br><span style='{sub_title_style}'>Overall Max: N/A | Overall Min: N/A</span>"
    
    # Custom axes configuration
    col_config1, col_config2, col_config3 = st.columns([1, 1, 1])
    with col_config1:
        use_custom = st.checkbox("Custom X-axis Bounds (Bar/Box Charts)", key=f"check_{col_str}")
    with col_config2:
        x_min = st.number_input("Min X", value=-1000.0, disabled=not use_custom, key=f"min_{col_str}")
    with col_config3:
        x_max = st.number_input("Max X", value=1000.0, disabled=not use_custom, key=f"max_{col_str}")
    
    # Prepare side-by-side columns for 3D View and Bar Chart
    col_plot1, col_plot2 = st.columns([1, 1])
    
    # 1. Render 3D Plot (Left Column)
    with col_plot1:
        x_lines, y_lines, z_lines, c_lines, text_lines = [], [], [], [], []
        for _, row in plot_elem_df.iterrows():
            val = row[col_str]
            x_lines.extend([row['Xi'], row['Xj'], None])
            y_lines.extend([row['Yi'], row['Yj'], None])
            z_lines.extend([row['Zi'], row['Zj'], None])
            c_lines.extend([val, val, val]) 
            hover_txt = f"<b>{row['Unique Name']}</b><br>Value: {val:,.2f}"
            text_lines.extend([hover_txt, hover_txt, ""])

        # Create Background Trace (Gray)
        trace_bg = go.Scatter3d(
            x=bg_x, y=bg_y, z=bg_z,
            mode='lines',
            line=dict(color='gray', width=0.5),
            hoverinfo='none',
            showlegend=False
        )

        # Create Colored Foreground Trace
        trace_fg = go.Scatter3d(
            x=x_lines, y=y_lines, z=z_lines,
            mode='lines',
            line=dict(
                color=c_lines,
                colorscale=c_scale,
                cmin=overall_min if not plot_df.empty else None,
                cmax=overall_max if not plot_df.empty else None,
                width=6,
                colorbar=dict(title="Force", thickness=15, len=0.75, y=0.5, yanchor='middle') 
            ),
            text=text_lines,
            hoverinfo='text',
            showlegend=False
        )
        
        # Combine traces
        fig_3d = go.Figure(data=[trace_bg, trace_fg])
        
        fig_3d.update_layout(
            title_text=fig3d_title, title_x=0.0,
            scene=dict(
                aspectmode='data',
                camera=dict(
                    eye=dict(x=2.5, y=2.5, z=2.5) 
                )
            ),
            margin=dict(l=0, r=0, b=0, t=80)
        )
        st.plotly_chart(fig_3d, use_container_width=True)

    # 2. Render Bar Chart (Right Column)
    with col_plot2:
        fig_bar = px.bar(
            plot_df, 
            x=col_str, 
            y="Story_Label", 
            orientation='h', 
            color=col_str,
            color_continuous_scale=c_scale,
            range_color=[overall_min, overall_max] if not plot_df.empty else None 
        )
        
        fig_bar.update_layout(
            title_text=bar_title, title_x=0.0, margin=dict(t=80),
            coloraxis_colorbar=dict(title="Force", thickness=15, len=0.75, y=0.5, yanchor='middle')
        )
        
        # --- FIX APPLIED HERE ---
        # Forces the y-axis to strictly display every story in the building, sorted correctly, 
        # stretching from -0.5 to length-0.5 so bars sit neatly on the ticks without dropping empty floors.
        fig_bar.update_yaxes(
            type='category',
            categoryorder='array', 
            categoryarray=master_story_labels,
            range=[-0.5, len(master_story_labels) - 0.5]
        )
        
        if use_custom: 
            fig_bar.update_xaxes(range=[x_min, x_max])
        st.plotly_chart(fig_bar, use_container_width=True)

    # 3. Render Box Plot (Bottom, full width)
    box_df = plot_df.copy()
    box_df['Element Force'] = col_str 
    
    fig_box = px.box(
        box_df, 
        x=col_str, 
        y='Element Force', 
        orientation='h', 
        points="all" 
    )
    
    fig_box.update_layout(title_text=box_title, title_x=0.0, margin=dict(t=80))
    fig_box.update_traces(pointpos=0, jitter=0.2)
    
    if use_custom: 
        fig_box.update_xaxes(range=[x_min, x_max])
    st.plotly_chart(fig_box, use_container_width=True)
    st.markdown("---")


# --- STEP 5: TABLES ---
st.header("Data Tables")

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
    cols = ['Maximum Type'] + [c for c in df_max_table.columns if c != 'Maximum Type']
    st.dataframe(df_max_table[cols], use_container_width=True)
else:
    st.info("No matching max rows to display for the current selection.")

st.subheader("Filtered Element Forces Data")
st.write(f"**Total Rows:** {len(filtered_df)}")

ordered_cols = [
    'Story', 'Unique Name', 'Group Name', 'Output Case', 
    'P', 'T', 'V2', 'M3', 'V3', 'M2', 
    'Length', 'UniquePtI', 'UniquePtJ', 'Xi', 'Yi', 'Zi', 'Xj', 'Yj', 'Zj', 'Analysis Section'
]
df_table_2 = filtered_df[ordered_cols]
st.dataframe(df_table_2, use_container_width=True)