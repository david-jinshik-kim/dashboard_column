import streamlit as st
import pandas as pd

@st.cache_data
def load_data(file_buffer):
    try: 
        xls = pd.ExcelFile(file_buffer, engine='calamine')
    except ValueError: 
        xls = pd.ExcelFile(file_buffer)
        
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