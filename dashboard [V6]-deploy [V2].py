import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import pickle
from pandas.api.types import is_numeric_dtype

st.set_page_config(layout="wide", page_title="Column Element Forces Dashboard")

st.title("Column Element Forces Dashboard")

# --- STEP 1: DUAL FILE UPLOAD & PRELOADED DATA ---
st.sidebar.header("Data Source")

# Now accepts Excel OR Pickle files
uploaded_file = st.sidebar.file_uploader("Upload ETABS Data", type=["xlsx", "xls", "pkl"])

query_params = st.query_params
url_dataset = query_params.get("dataset") 

# Determine data source and file type
if uploaded_file is not None:
    data_source = uploaded_file
    file_ext = uploaded_file.name.split('.')[-1].lower()
    st.sidebar.success("✅ Using uploaded file.")

# For preloaded links, we assume you uploaded optimized .pkl files to GitHub
elif url_dataset and os.path.exists(f"{url_dataset}.pkl"):
    data_source = f"{url_dataset}.pkl"
    file_ext = "pkl"
    st.sidebar.info(f"ℹ️ Using preloaded optimized data: **{url_dataset}**")

else:
    st.info("👋 Please upload your ETABS Element Forces file (.xlsx or .pkl) using the sidebar, or use a valid project link.")
    st.stop()


# --- STEP 2: HYBRID LOAD AND MERGE ---
@st.cache_data
def load_data(file_buffer, ext):
    
    # SCENARIO A: User is using a preloaded link or uploaded a .pkl file
    if ext == "pkl":
        if hasattr(file_buffer, 'read'):
            master_df = pickle.load(file_buffer)
        else:
            with open(file_buffer, "rb") as f:
                master_df = pickle.load(f)
        return master_df
        
    # SCENARIO B: User uploaded a raw Excel file
    else:
        # We use the 'calamine' engine to prevent Streamlit Cloud from crashing!
        try:
            xls = pd.ExcelFile(file_buffer, engine='calamine')
        except ValueError:
            # Fallback just in case calamine isn't installed
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
    df = load_data(data_source, file_ext)
except Exception as e:
    st.error(f"Error processing the file. Error Details: {e}")
    st.stop()


# --- STEP 3: DASHBOARD SLICERS (SIDEBAR) ---
st.sidebar.markdown("---")
st.sidebar.header("Dashboard Filters")

# Initialize toggle counters in session state so the widget keys never repeat
if 'grp_count' not in st.session_state: st.session_state.grp_count = 0
if 'sty_count' not in st.session_state: st.session_state.sty_count = 0
if 'cas_count' not in st.session_state: st.session_state.cas_count = 0

def bump_grp(): st.session_state.grp_count += 1
def bump_sty(): st.session_state.sty_count += 1
def bump_cas(): st.session_state.cas_count += 1

# 1. Group Names Filter with Search
all_groups_list = sorted(list(set(g for g_str in df['Group Name'].dropna() for g in g_str.split(', '))))
group_search = st.sidebar.text_input("🔍 Search Groups:", key="search_groups")
filtered_groups_list = [g for g in all_groups_list if group_search.lower() in g.lower()] if group_search else all_groups_list

all_groups_chk = st.sidebar.checkbox(
    f"Select All ({len(filtered_groups_list)} Matches)", 
    value=True, 
    key="chk_groups",
    on_change=bump_grp
)

# Key is now unique forever (e.g., ms_groups_0, ms_groups_1, ms_groups_2)
group_ms_key = f"ms_groups_{group_search}_{st.session_state.grp_count}"

if all_groups_chk:
    selected_groups = st.sidebar.multiselect("Select Group Name(s):", options=filtered_groups_list, default=filtered_groups_list, key=group_ms_key)
else:
    selected_groups = st.sidebar.multiselect("Select Group Name(s):", options=filtered_groups_list, default=filtered_groups_list[:1] if filtered_groups_list else [], key=group_ms_key)

st.sidebar.markdown("---")

# 2. Stories Filter with Search
stories_list = sorted(df['Story'].dropna().unique().tolist())
story_search = st.sidebar.text_input("🔍 Search Stories:", key="search_stories")
filtered_stories_list = [s for s in stories_list if story_search.lower() in s.lower()] if story_search else stories_list

all_stories_chk = st.sidebar.checkbox(
    f"Select All ({len(filtered_stories_list)} Matches)", 
    value=True, 
    key="chk_stories",
    on_change=bump_sty
)

story_ms_key = f"ms_stories_{story_search}_{st.session_state.sty_count}"

if all_stories_chk:
    selected_stories = st.sidebar.multiselect("Select Story(ies):", options=filtered_stories_list, default=filtered_stories_list, key=story_ms_key)
else:
    selected_stories = st.sidebar.multiselect("Select Story(ies):", options=filtered_stories_list, default=filtered_stories_list[:1] if filtered_stories_list else [], key=story_ms_key)

st.sidebar.markdown("---")

# 3. Output Cases Filter with Search
cases_list = sorted(df['Output Case'].dropna().unique().tolist())
case_search = st.sidebar.text_input("🔍 Search Cases:", key="search_cases")
filtered_cases_list = [c for c in cases_list if case_search.lower() in c.lower()] if case_search else cases_list

all_cases_chk = st.sidebar.checkbox(
    f"Select All ({len(filtered_cases_list)} Matches)", 
    value=True, 
    key="chk_cases",
    on_change=bump_cas
)

cases_ms_key = f"ms_cases_{case_search}_{st.session_state.cas_count}"

if all_cases_chk:
    selected_cases = st.sidebar.multiselect("Select Output Case(s):", options=filtered_cases_list, default=filtered_cases_list, key=cases_ms_key)
else:
    selected_cases = st.sidebar.multiselect("Select Output Case(s):", options=filtered_cases_list, default=filtered_cases_list[:5] if len(filtered_cases_list) >= 5 else filtered_cases_list, key=cases_ms_key)


def filter_groups(row_group_str, selected_groups_list):
    if pd.isna(row_group_str): return False
    row_groups = row_group_str.split(', ')
    return any(g in selected_groups_list for g in row_groups)

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

# Compute Individual Element Aggregations
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
    
    col_config1, col_config2, col_config3 = st.columns([1, 1, 1])
    with col_config1:
        use_custom = st.checkbox("Custom X-axis Bounds (Bar/Box Charts)", key=f"check_{col_str}")
    with col_config2:
        x_min = st.number_input("Min X", value=-1000.0, disabled=not use_custom, key=f"min_{col_str}")
    with col_config3:
        x_max = st.number_input("Max X", value=1000.0, disabled=not use_custom, key=f"max_{col_str}")
    
    col_plot1, col_plot2 = st.columns([1, 1])
    
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

        trace_bg = go.Scatter3d(
            x=bg_x, y=bg_y, z=bg_z,
            mode='lines',
            line=dict(color='gray', width=0.5),
            hoverinfo='none',
            showlegend=False
        )

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
        
        fig_3d = go.Figure(data=[trace_bg, trace_fg])
        
        fig_3d.update_layout(
            title_text=fig3d_title, title_x=0.0,
            scene=dict(
                aspectmode='data',
                camera=dict(eye=dict(x=2.5, y=2.5, z=2.5)) 
            ),
            margin=dict(l=0, r=0, b=0, t=80)
        )
        st.plotly_chart(fig_3d, use_container_width=True)

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
        
        fig_bar.update_yaxes(
            type='category',
            categoryorder='array', 
            categoryarray=master_story_labels,
            range=[-0.5, len(master_story_labels) - 0.5]
        )
        
        if use_custom: 
            fig_bar.update_xaxes(range=[x_min, x_max])
        st.plotly_chart(fig_bar, use_container_width=True)

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

# --- STEP 5: TABLES WITH COLUMN FILTERS ---
st.header("Data Tables")

# Define the shared column order for both tables
ordered_cols = [
    'Story', 'Unique Name', 'Group Name', 'Output Case', 
    'P', 'T', 'V2', 'M3', 'V3', 'M2', 
    'Length', 'UniquePtI', 'UniquePtJ', 'Xi', 'Yi', 'Zi', 'Xj', 'Yj', 'Zj', 'Analysis Section'
]

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
    
    # Apply the custom ordered columns, putting 'Maximum Type' at the very beginning
    max_table_cols = ['Maximum Type'] + [c for c in ordered_cols if c in df_max_table.columns]
    target_max_df = df_max_table[max_table_cols]
    
    # Render the dataframe and capture the selection event
    max_selection_event = st.dataframe(
        target_max_df, 
        use_container_width=True,
        on_select="rerun",
        selection_mode=["multi-row", "multi-column"]
    )
    
    # Extract selected rows and columns
    max_selected_rows = max_selection_event.selection.rows
    max_selected_cols = max_selection_event.selection.columns
    
    # If the user has highlighted anything, generate a targeted dataframe and show a download button
    if max_selected_rows or max_selected_cols:
        
        # Logic to handle if they only selected rows, only columns, or both
        if max_selected_rows and not max_selected_cols:
            max_subset_df = target_max_df.iloc[max_selected_rows]
        elif max_selected_cols and not max_selected_rows:
            max_subset_df = target_max_df[max_selected_cols]
        else:
            # Both rows and columns selected
            max_subset_df = target_max_df.iloc[max_selected_rows][max_selected_cols]
            
        # Convert subset to CSV format
        max_csv_data = max_subset_df.to_csv(index=False).encode('utf-8')
        
        st.success(f"You have selected {len(max_subset_df)} rows and {len(max_subset_df.columns)} columns.")
        st.download_button(
            label="📥 Download Max Forces Selection for Excel",
            data=max_csv_data,
            file_name="etabs_max_forces_selection.csv",
            mime="text/csv",
            type="primary",
            key="download_max_forces" # Unique key required!
        )
else:
    st.info("No matching max rows to display for the current selection.")


st.subheader("Filtered Element Forces Data")

df_table_2 = filtered_df[ordered_cols].copy()

# --- NEW: Dynamic Column Filtering UI ---
modify = st.checkbox("🔍 Add Column Filters")

if modify:
    df_to_filter = df_table_2.copy()
    with st.expander("Filter columns", expanded=True):
        to_filter_columns = st.multiselect("Select columns to filter:", df_to_filter.columns)
        
        for column in to_filter_columns:
            left, right = st.columns((1, 20))
            left.write("↳")
            
            if is_numeric_dtype(df_to_filter[column]):
                _min = float(df_to_filter[column].min())
                _max = float(df_to_filter[column].max())
                step = (_max - _min) / 100 if (_max - _min) > 0 else 1.0
                
                user_num_input = right.slider(
                    f"Values for {column}",
                    min_value=_min,
                    max_value=_max,
                    value=(_min, _max),
                    step=step,
                )
                df_to_filter = df_to_filter[df_to_filter[column].between(*user_num_input)]
                
            else:
                user_cat_input = right.multiselect(
                    f"Values for {column}",
                    options=df_to_filter[column].dropna().unique(),
                    default=df_to_filter[column].dropna().unique(),
                )
                df_to_filter = df_to_filter[df_to_filter[column].isin(user_cat_input)]
                
    st.write(f"**Total Filtered Rows:** {len(df_to_filter)}")
    target_df = df_to_filter
else:
    st.write(f"**Total Rows:** {len(df_table_2)}")
    target_df = df_table_2

# Render the dataframe and capture the selection event
selection_event = st.dataframe(
    target_df, 
    use_container_width=True,
    on_select="rerun",
    selection_mode=["multi-row", "multi-column"]
)

# Extract selected rows and columns
selected_rows = selection_event.selection.rows
selected_cols = selection_event.selection.columns

# If the user has highlighted anything, generate a targeted dataframe and show a download button
if selected_rows or selected_cols:
    
    if selected_rows and not selected_cols:
        subset_df = target_df.iloc[selected_rows]
    elif selected_cols and not selected_rows:
        subset_df = target_df[selected_cols]
    else:
        subset_df = target_df.iloc[selected_rows][selected_cols]
        
    csv_data = subset_df.to_csv(index=False).encode('utf-8')
    
    st.success(f"You have selected {len(subset_df)} rows and {len(subset_df.columns)} columns.")
    st.download_button(
        label="📥 Download Selection for Excel",
        data=csv_data,
        file_name="etabs_selection.csv",
        mime="text/csv",
        type="primary",
        key="download_filtered_forces" # Unique key required!
    )