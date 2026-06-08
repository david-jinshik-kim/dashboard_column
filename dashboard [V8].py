import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import io
import zipfile
from typing import Any
from pandas.api.types import is_numeric_dtype

# ==============================================================================
# --- S-CONCRETE PARSER ---
# ==============================================================================

def _try_numeric(value: str) -> Any:
    v = value.strip()
    try: return int(v)
    except ValueError: pass
    try: return float(v)
    except ValueError: pass
    return v

def _fmt_value(raw_original: str, new_value: Any) -> str:
    leading = " " if raw_original.startswith(" ") else ""
    if isinstance(new_value, float): return f"{leading}{new_value:.6g}"
    if isinstance(new_value, int): return f"{leading}{new_value}"
    return str(new_value)

class KVTable:
    def __init__(self, raw_lines: list[str]):
        self.params: dict[str, Any] = {}
        self.param_order: list[str] = []
        self._raw_values: dict[str, str] = {}
        self._param_line: dict[str, int] = {}
        self._raw_lines: list[str] = list(raw_lines)
        self._dirty: set[str] = set()
        self._parse()

    def _parse(self):
        for line_idx, line in enumerate(self._raw_lines):
            tokens = line.split("\t")
            i = 0
            while i < len(tokens):
                key = tokens[i].strip()
                i += 1
                if key == "": continue
                raw_val = tokens[i] if i < len(tokens) else ""
                i += 1
                value = _try_numeric(raw_val) if raw_val.strip() != "" else raw_val.strip()
                if key not in self.params: self.param_order.append(key)
                self.params[key] = value
                self._raw_values[key] = raw_val
                self._param_line[key] = line_idx

    def set(self, param: str, value: Any) -> bool:
        if param not in self.params: return False
        self.params[param] = value
        self._dirty.add(param)
        return True

    def to_lines(self) -> list[str]:
        dirty_idxs = {self._param_line[p] for p in self._dirty if p in self._param_line}
        out: list[str] = []
        for idx, raw_line in enumerate(self._raw_lines):
            if idx not in dirty_idxs:
                out.append(raw_line)
            else:
                tokens = raw_line.split("\t")
                i = 0
                new_tokens: list[str] = []
                while i < len(tokens):
                    key = tokens[i].strip()
                    if key == "" or i + 1 >= len(tokens):
                        new_tokens.append(tokens[i])
                        i += 1
                        continue
                    raw_val = tokens[i + 1]
                    new_tokens.append(tokens[i])
                    new_tokens.append(_fmt_value(raw_val, self.params[key]) if key in self._dirty else raw_val)
                    i += 2
                out.append("\t".join(new_tokens))
        return out

class TabularTable:
    def __init__(self, raw_lines: list[str]):
        self._raw_lines: list[str] = list(raw_lines)
        self._raw_header: str = ""
        self._raw_rows: list[str] = []
        self.columns: list[str] = []
        self.rows: list[dict[str, Any]] = []
        self._dirty: bool = False
        self._parse()

    def _parse(self):
        if not self._raw_lines: return
        self._raw_header = self._raw_lines[0]
        self.columns = [c.strip() for c in self._raw_header.split("\t")]
        for line in self._raw_lines[1:]:
            if not line.strip(): continue
            self._raw_rows.append(line)
            values = [_try_numeric(v) for v in line.split("\t")]
            while len(values) < len(self.columns): values.append("")
            self.rows.append(dict(zip(self.columns, values)))

    def set_rows(self, new_rows: list[dict[str, Any]]):
        self.rows = list(new_rows)
        self._dirty = True

    def to_lines(self) -> list[str]:
        out = [self._raw_header]
        if not self._dirty:
            out.extend(self._raw_rows)
        else:
            for row in self.rows:
                cells = [str(row.get(col, "")) for col in self.columns]
                out.append("\t".join(cells))
        return out

_TABULAR_OBJECTS: frozenset[str] = frozenset({
    "S-CONCRETE Customized Bar Information", "S-CONCRETE Panel Information",
    "S-CONCRETE Zone Information", "S-CONCRETE Sectional Loads", "S-CONCRETE Panel Loads",
})

class ScoObject:
    def __init__(self, name: str, obj_line: str, table_line: str, data_lines: list[str]):
        self.name = name
        self._obj_line = obj_line
        self._table_line = table_line
        self.table: KVTable | TabularTable = TabularTable(data_lines) if name in _TABULAR_OBJECTS else KVTable(data_lines)

    @property
    def is_kv(self) -> bool: return isinstance(self.table, KVTable)
    @property
    def is_tabular(self) -> bool: return isinstance(self.table, TabularTable)

    def to_lines(self) -> list[str]:
        return [self._obj_line, self._table_line] + self.table.to_lines() + ["@EndTable@"]

class ScoFile:
    def __init__(self, raw_text: str):
        self._preamble_lines: list[str] = []
        self.objects: list[ScoObject] = []
        self._load(raw_text)

    def _load(self, raw_text: str):
        lines = raw_text.splitlines(keepends=False)
        current_name, current_obj_line, current_table_line = "", "", ""
        current_data: list[str] = []
        in_table, seen_object = False, False

        for line in lines:
            s = line.strip()
            if s.startswith("@Object@"):
                seen_object = True
                parts = s.split("@")
                current_name = parts[2].strip() if len(parts) > 2 else s
                current_obj_line = line
                current_table_line = ""
                current_data = []
                in_table = False
            elif s.startswith("@Table@"):
                current_table_line = line
                in_table = True
            elif s == "@EndTable@":
                self.objects.append(ScoObject(current_name, current_obj_line, current_table_line, current_data))
                current_data = []
                in_table = False
            elif in_table:
                current_data.append(line)
            elif not seen_object:
                self._preamble_lines.append(line)

    def get_object(self, name: str) -> ScoObject | None:
        nl = name.lower()
        for obj in self.objects:
            if nl in obj.name.lower(): return obj
        return None

    @property
    def sectional_loads(self) -> TabularTable | None:
        obj = self.get_object("Sectional Loads")
        return obj.table if (obj and obj.is_tabular) else None

    def _kv_objects(self) -> list[ScoObject]: return [o for o in self.objects if o.is_kv]

    def set_params(self, updates: dict[str, Any]) -> dict[str, bool]:
        results = {}
        for k, v in updates.items():
            success = False
            for obj in self._kv_objects():
                if obj.table.set(k, v):
                    success = True
                    break
            results[k] = success
        return results

    def _serialise(self) -> str:
        all_lines: list[str] = list(self._preamble_lines)
        for obj in self.objects: all_lines.extend(obj.to_lines())
        return "\r\n".join(all_lines) + "\r\n"

# ==============================================================================
# --- STREAMLIT DASHBOARD CONFIG ---
# ==============================================================================

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
    try: xls = pd.ExcelFile(file_buffer, engine='calamine')
    except ValueError: xls = pd.ExcelFile(file_buffer)
        
    def read_etabs_sheet(excel_obj, sheet_name):
        df = pd.read_excel(excel_obj, sheet_name=sheet_name, skiprows=[0])
        return df.drop(index=0).reset_index(drop=True)

    df_forces = read_etabs_sheet(xls, "Element Forces - Columns")
    df_conn = read_etabs_sheet(xls, "Column Object Connectivity")
    df_pts = read_etabs_sheet(xls, "Point Object Connectivity")
    df_frame = read_etabs_sheet(xls, "Frame Assigns - Summary")
    df_groups = read_etabs_sheet(xls, "Group Assignments")

    for col in ['P', 'T', 'V2', 'V3', 'M2', 'M3']:
        df_forces[col] = pd.to_numeric(df_forces[col], errors='coerce')

    df_conn = df_conn[['Unique Name', 'Length', 'UniquePtI', 'UniquePtJ']]
    master_df = pd.merge(df_forces, df_conn, on='Unique Name', how='left')

    df_pts_clean = df_pts[['UniqueName', 'X', 'Y', 'Z']].rename(columns={'UniqueName': 'PointId'})
    master_df = pd.merge(master_df, df_pts_clean.rename(columns={'PointId': 'UniquePtI', 'X': 'Xi', 'Y': 'Yi', 'Z': 'Zi'}), on='UniquePtI', how='left')
    master_df = pd.merge(master_df, df_pts_clean.rename(columns={'PointId': 'UniquePtJ', 'X': 'Xj', 'Y': 'Yj', 'Z': 'Zj'}), on='UniquePtJ', how='left')

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
    st.error(f"Error processing the Excel file. Details: {e}")
    st.stop()

# --- STEP 3: DASHBOARD SLICERS (SIDEBAR) ---
st.sidebar.markdown("---")
st.sidebar.header("Dashboard Filters")

if 'grp_count' not in st.session_state: st.session_state.grp_count = 0
if 'sty_count' not in st.session_state: st.session_state.sty_count = 0
if 'cas_count' not in st.session_state: st.session_state.cas_count = 0

def bump_grp(): st.session_state.grp_count += 1
def bump_sty(): st.session_state.sty_count += 1
def bump_cas(): st.session_state.cas_count += 1

all_groups_list = sorted(list(set(g for g_str in df['Group Name'].dropna() for g in g_str.split(', '))))
group_search = st.sidebar.text_input("🔍 Search Groups:", key="search_groups")
filtered_groups_list = [g for g in all_groups_list if group_search.lower() in g.lower()] if group_search else all_groups_list
all_groups_chk = st.sidebar.checkbox(f"Select All ({len(filtered_groups_list)} Matches)", value=True, key="chk_groups", on_change=bump_grp)
group_ms_key = f"ms_groups_{group_search}_{st.session_state.grp_count}"
selected_groups = st.sidebar.multiselect("Select Group Name(s):", options=filtered_groups_list, default=filtered_groups_list if all_groups_chk else filtered_groups_list[:1], key=group_ms_key)

stories_list = sorted(df['Story'].dropna().unique().tolist())
story_search = st.sidebar.text_input("🔍 Search Stories:", key="search_stories")
filtered_stories_list = [s for s in stories_list if story_search.lower() in s.lower()] if story_search else stories_list
all_stories_chk = st.sidebar.checkbox(f"Select All ({len(filtered_stories_list)} Matches)", value=True, key="chk_stories", on_change=bump_sty)
story_ms_key = f"ms_stories_{story_search}_{st.session_state.sty_count}"
selected_stories = st.sidebar.multiselect("Select Story(ies):", options=filtered_stories_list, default=filtered_stories_list if all_stories_chk else filtered_stories_list[:1], key=story_ms_key)

cases_list = sorted(df['Output Case'].dropna().unique().tolist())
case_search = st.sidebar.text_input("🔍 Search Cases:", key="search_cases")
filtered_cases_list = [c for c in cases_list if case_search.lower() in c.lower()] if case_search else cases_list
all_cases_chk = st.sidebar.checkbox(f"Select All ({len(filtered_cases_list)} Matches)", value=True, key="chk_cases", on_change=bump_cas)
cases_ms_key = f"ms_cases_{case_search}_{st.session_state.cas_count}"
selected_cases = st.sidebar.multiselect("Select Output Case(s):", options=filtered_cases_list, default=filtered_cases_list if all_cases_chk else filtered_cases_list[:5], key=cases_ms_key)

def filter_groups(row_group_str, selected_groups_list):
    if pd.isna(row_group_str): return False
    return any(g in selected_groups_list for g in row_group_str.split(', '))

mask = df['Group Name'].apply(lambda x: filter_groups(x, selected_groups)) & df['Story'].isin(selected_stories) & df['Output Case'].isin(selected_cases)
filtered_df = df[mask].copy()

if filtered_df.empty:
    st.warning("No data matches the current filter selections.")
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
    if s == 'BASE': return -999 
    if 'ROOF' in s: return 999
    m_b = re.search(r'B(\d+)', s)
    if m_b: return -int(m_b.group(1)) 
    m = re.search(r'\d+', s)
    if m: return int(m.group())
    return 0

def format_story_label(story_str):
    s = str(story_str)
    if s.upper() == 'BASE': return 'Base'
    return s.replace('F', '').replace('f', '')

all_unique_stories = df['Story'].dropna().unique()
master_stories = [{"Story_Num": get_story_num(s), "Story_Label": format_story_label(s)} for s in all_unique_stories]
master_story_labels = pd.DataFrame(master_stories).sort_values("Story_Num")['Story_Label'].tolist()

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
if not df_summary.empty:
    df_summary = df_summary.sort_values(by="Story_Num")
else:
    expected_story_cols = ["Story", "Story_Num", "Story_Label"] + [c['label'] for c in force_configs]
    df_summary = pd.DataFrame(columns=expected_story_cols)

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
if df_elem_summary.empty:
    expected_elem_cols = ["Unique Name", "Xi", "Yi", "Zi", "Xj", "Yj", "Zj"] + [c['label'] for c in force_configs]
    df_elem_summary = pd.DataFrame(columns=expected_elem_cols)

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
        use_custom = st.checkbox("Custom Bounds & Color Scale", key=f"check_{col_str}")
    with col_config2:
        x_min = st.number_input("Min X", value=-1000.0, disabled=not use_custom, key=f"min_{col_str}")
    with col_config3:
        x_max = st.number_input("Max X", value=1000.0, disabled=not use_custom, key=f"max_{col_str}")
    
    if use_custom:
        c_min_val = x_min
        c_max_val = x_max
    else:
        c_min_val = overall_min if not plot_df.empty else 0.0
        c_max_val = overall_max if not plot_df.empty else 0.0

    shared_colorbar = dict(
        title="Force",
        thickness=15,
        lenmode='pixels',
        len=400,           
        y=0.5,
        yanchor='middle'
    )

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
                cmin=c_min_val,
                cmax=c_max_val,
                width=6,
                colorbar=shared_colorbar
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
            margin=dict(l=0, r=0, b=0, t=80),
            height=600
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
            range_color=[c_min_val, c_max_val]
        )
        fig_bar.update_layout(
            title_text=bar_title, title_x=0.0, 
            margin=dict(l=0, r=0, b=0, t=80),
            height=600, 
            coloraxis_colorbar=shared_colorbar
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

# --- STEP 5: DATA TABLES & SCO EXPORT ---
st.header("Data Tables & S-CONCRETE Export")

ordered_cols = ['Story', 'Unique Name', 'Group Name', 'Output Case', 'P', 'T', 'V2', 'M3', 'V3', 'M2', 'Length', 'UniquePtI', 'UniquePtJ', 'Xi', 'Yi', 'Zi', 'Xj', 'Yj', 'Zj', 'Analysis Section']
df_table = filtered_df[ordered_cols].copy()

st.write(f"**Total Filtered Rows:** {len(df_table)}")

# Render dataframe and catch selections
selection_event = st.dataframe(
    df_table, 
    use_container_width=True,
    on_select="rerun",
    selection_mode=["multi-row", "multi-column"]
)

selected_rows = selection_event.selection.rows

if selected_rows:
    subset_df = df_table.iloc[selected_rows]
    st.success(f"✅ You have selected {len(subset_df)} rows. You can now generate SCO files or download CSV.")
    
    col_csv, col_sco = st.columns([1, 1])
    
    # Standard CSV Download
    with col_csv:
        csv_data = subset_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Selection as CSV", data=csv_data, file_name="etabs_selection.csv", mime="text/csv", type="secondary")
        
    # SCO Generation UI
    st.markdown("### 🔨 Generate S-CONCRETE (.SCO) Files")
    st.info("Upload a template `.SCO` file below. A zipped folder will be generated, grouping columns by their **Group Name**.")
    
    sco_template_file = st.file_uploader("Upload Template .SCO", type=["sco"])
    
    if sco_template_file is not None:
        raw_template_text = sco_template_file.getvalue().decode('latin-1')
        
        # Build the ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            
            # Future Proofing: Group by Group Name, then Unique Name
            for group_name, group_df in subset_df.groupby("Group Name"):
                
                # Replace slashes with underscores to prevent accidental sub-folder creation
                safe_group_str = str(group_name).replace("/", "_").replace("\\", "_")
                # Allow periods (.), spaces, dashes, and underscores
                safe_group_dir = "".join([c for c in safe_group_str if c.isalnum() or c in " _-."]).strip()
                
                for unique_name, col_df in group_df.groupby("Unique Name"):
                    
                    safe_col_str = str(unique_name).replace("/", "_").replace("\\", "_")
                    safe_col_name = "".join([c for c in safe_col_str if c.isalnum() or c in " _-."]).strip()
                    
                    # 1. Instantiate fresh template parser
                    sco = ScoFile(raw_template_text)
                    
                    # 2. Extract dimensions from "Analysis Section"
                    section_str = str(col_df['Analysis Section'].iloc[0])
                    dims = [float(d) for d in re.findall(r'\d+', section_str)]
                    
                    bcol = dims[0] if len(dims) > 0 else 500  # Default to 500 if parsing fails
                    hcol = dims[1] if len(dims) > 1 else bcol
                    
                    # 3. Extract Length
                    length = float(col_df['Length'].iloc[0])
                    
                    # 4. Set KV Parameters
                    sco.set_params({
                        "Cm bcol": bcol,
                        "Cm hcol": hcol,
                        "Cm D": bcol,  # Fallback for circular columns
                        "LuYY": length,
                        "LuZZ": length,
                        "Member Name": unique_name
                    })
                    
                    # 5. Build Sectional Loads Table
                    load_rows = []
                    for idx, row in enumerate(col_df.to_dict('records')):
                        # Maps ETABS loads directly to S-CONCRETE table
                        # Multiplied row['P'] by -1 to match S-CONCRETE sign convention
                        load_row = {
                            'LC': idx + 1,
                            'Nf': row['P'], 
                            'Tf': row['T'],
                            'Vfz': row['V3'],
                            'Mfy': row['M2'],
                            'Cmy': 1,
                            'Vfy': row['V2'],
                            'Mfz': row['M3'],
                            'Cmz': 1,
                            'Pdistr': 0,
                            'CheckLC': 1,
                            'Load Type': 1,
                            'Comment': row['Output Case'], 
                            'AutoGen': 0,
                            'SustFactor': 1,
                            'ServLdFactor': 1
                        }
                        load_rows.append(load_row)
                    
                    if sco.sectional_loads:
                        sco.sectional_loads.set_rows(load_rows)
                    
                    # 6. Write to Zip directory: Group_Name/Unique_Name.sco
                    file_content = sco._serialise()
                    zip_path = f"{safe_group_dir}/{safe_col_name}.SCO"
                    zip_file.writestr(zip_path, file_content.encode('latin-1'))
        
        # Present the download button immediately
        st.success(f"Successfully generated SCO files for {len(subset_df['Unique Name'].unique())} unique columns.")
        st.download_button(
            label="📥 Download Generated SCO Files (.zip)",
            data=zip_buffer.getvalue(),
            file_name="S_CONCRETE_Export.zip",
            mime="application/zip",
            type="primary"
        )