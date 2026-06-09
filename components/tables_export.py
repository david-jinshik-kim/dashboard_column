import streamlit as st
import pandas as pd
import io
import zipfile
import re
from pandas.api.types import is_numeric_dtype
from core.sco_parser import ScoFile

def render_tables_and_export(filtered_df, force_configs):
    st.header("Data Tables & S-CONCRETE Export")
    ordered_cols = ['Story', 'Unique Name', 'Group Name', 'Output Case', 'P', 'T', 'V2', 'M3', 'V3', 'M2', 'Length', 'UniquePtI', 'UniquePtJ', 'Xi', 'Yi', 'Zi', 'Xj', 'Yj', 'Zj', 'Analysis Section']

    # --- MAX TABLE ---
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
        max_table_cols = ['Maximum Type'] + [c for c in ordered_cols if c in df_max_table.columns]
        target_max_df = df_max_table[max_table_cols]
        
        max_selection_event = st.dataframe(target_max_df, use_container_width=True, on_select="rerun", selection_mode=["multi-row", "multi-column"])
        
        max_selected_rows = max_selection_event.selection.rows
        max_selected_cols = max_selection_event.selection.columns
        
        if max_selected_rows or max_selected_cols:
            if max_selected_rows and not max_selected_cols:
                max_subset_df = target_max_df.iloc[max_selected_rows]
            elif max_selected_cols and not max_selected_rows:
                max_subset_df = target_max_df[max_selected_cols]
            else:
                max_subset_df = target_max_df.iloc[max_selected_rows][max_selected_cols]
                
            max_csv_data = max_subset_df.to_csv(index=False).encode('utf-8')
            st.success(f"You have selected {len(max_subset_df)} rows and {len(max_subset_df.columns)} columns.")
            st.download_button(label="📥 Download Max Forces Selection for Excel", data=max_csv_data, file_name="etabs_max_forces_selection.csv", mime="text/csv", type="primary", key="download_max_forces")
    else:
        st.info("No matching max rows to display for the current selection.")

    # --- FILTERED MAIN TABLE ---
    st.subheader("Filtered Element Forces Data")
    df_table_2 = filtered_df[ordered_cols].copy()
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
                    user_num_input = right.slider(f"Values for {column}", min_value=_min, max_value=_max, value=(_min, _max), step=step)
                    df_to_filter = df_to_filter[df_to_filter[column].between(*user_num_input)]
                else:
                    user_cat_input = right.multiselect(f"Values for {column}", options=df_to_filter[column].dropna().unique(), default=df_to_filter[column].dropna().unique())
                    df_to_filter = df_to_filter[df_to_filter[column].isin(user_cat_input)]
                    
        st.write(f"**Total Filtered Rows:** {len(df_to_filter)}")
        target_df = df_to_filter
    else:
        st.write(f"**Total Rows:** {len(df_table_2)}")
        target_df = df_table_2

    selection_event = st.dataframe(target_df, use_container_width=True, on_select="rerun", selection_mode=["multi-row", "multi-column"])
    selected_rows = selection_event.selection.rows

    if selected_rows:
        subset_df = target_df.iloc[selected_rows]
        st.success(f"✅ You have selected {len(subset_df)} rows. You can now generate SCO files or download CSV.")
        
        col_csv, col_sco = st.columns([1, 1])
        with col_csv:
            csv_data = subset_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Selection as CSV", data=csv_data, file_name="etabs_selection.csv", mime="text/csv", type="secondary")
            
        st.markdown("### 🔨 Generate S-CONCRETE (.SCO) Files")
        st.info("Upload a template `.SCO` file below. A zipped folder will be generated, grouping columns by their **Group Name**.")
        sco_template_file = st.file_uploader("Upload Template .SCO", type=["sco"])
        
        if sco_template_file is not None:
            raw_template_text = sco_template_file.getvalue().decode('latin-1')
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for group_name, group_df in subset_df.groupby("Group Name"):
                    safe_group_str = str(group_name).replace("/", "_").replace("\\", "_")
                    safe_group_dir = "".join([c for c in safe_group_str if c.isalnum() or c in " _-."]).strip()
                    
                    for unique_name, col_df in group_df.groupby("Unique Name"):
                        safe_col_str = str(unique_name).replace("/", "_").replace("\\", "_")
                        safe_col_name = "".join([c for c in safe_col_str if c.isalnum() or c in " _-."]).strip()
                        
                        sco = ScoFile(raw_template_text)
                        
                        section_str = str(col_df['Analysis Section'].iloc[0])
                        dims = [float(d) for d in re.findall(r'\d+', section_str)]
                        bcol = dims[0] if len(dims) > 0 else 500  
                        hcol = dims[1] if len(dims) > 1 else bcol
                        
                        # Grab max length across the grouped column
                        length = float(col_df['Length'].max())
                        
                        sco.set_params({
                            "Cm bcol": bcol,
                            "Cm hcol": hcol,
                            "Cm D": bcol, 
                            "LuYY": length,
                            "LuZZ": length,
                            "Member Name": unique_name
                        })
                        
                        load_rows = []
                        for idx, row in enumerate(col_df.to_dict('records')):
                            load_row = {
                                'LC': idx + 1,
                                'Nf': row['P'], 
                                'Tf': row['T'],
                                'Vfz': row['V2'],
                                'Mfy': row['M3'],
                                'Cmy': 1,
                                'Vfy': row['V3'],
                                'Mfz': row['M2'],
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
                        
                        file_content = sco._serialise()
                        zip_path = f"{safe_group_dir}/{safe_col_name}.SCO"
                        zip_file.writestr(zip_path, file_content.encode('latin-1'))
            
            st.success(f"Successfully generated SCO files for {len(subset_df['Unique Name'].unique())} unique columns.")
            st.download_button(label="📥 Download Generated SCO Files (.zip)", data=zip_buffer.getvalue(), file_name="S_CONCRETE_Export.zip", mime="application/zip", type="primary")