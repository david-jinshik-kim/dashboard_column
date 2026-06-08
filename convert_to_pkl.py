import pandas as pd
import pickle
import tkinter as tk
from tkinter import filedialog
import os

def read_etabs_sheet(excel_obj, sheet_name):
    df = pd.read_excel(excel_obj, sheet_name=sheet_name, skiprows=[0])
    df = df.drop(index=0).reset_index(drop=True)
    return df

def convert_excel_to_pkl():
    # Hide the main tkinter window
    root = tk.Tk()
    root.withdraw()

    print("🔍 Please select the ETABS Excel file to convert...")
    input_path = filedialog.askopenfilename(
        title="Select ETABS Excel File",
        filetypes=[("Excel Files", "*.xlsx *.xls")]
    )
    
    if not input_path:
        print("❌ No file selected. Canceling.")
        return

    print(f"\n📂 Loading: {os.path.basename(input_path)}")
    print("⏳ Reading Excel file (this may take a minute for large files)...")
    
    try:
        xls = pd.ExcelFile(input_path, engine='calamine')
    except ValueError:
        print("⚠️ 'calamine' engine not found locally. Falling back to standard Pandas (slower).")
        xls = pd.ExcelFile(input_path)

    print("⚙️ Extracting and merging sheets...")
    
    # 1. Extract Sheets
    df_forces = read_etabs_sheet(xls, "Element Forces - Columns")
    df_conn = read_etabs_sheet(xls, "Column Object Connectivity")
    df_pts = read_etabs_sheet(xls, "Point Object Connectivity")
    df_frame = read_etabs_sheet(xls, "Frame Assigns - Summary")
    df_groups = read_etabs_sheet(xls, "Group Assignments")

    # 2. Process Data
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
    master_df = master_df[cols_to_keep]

    # 3. Save the File
    print("💾 Please choose where to save the optimized Pickle file...")
    default_out_name = os.path.splitext(os.path.basename(input_path))[0] + "_Optimized.pkl"
    output_path = filedialog.asksaveasfilename(
        title="Save Optimized Pickle File",
        initialfile=default_out_name,
        defaultextension=".pkl",
        filetypes=[("Pickle Files", "*.pkl")]
    )

    if not output_path:
        print("❌ Save canceled.")
        return

    with open(output_path, "wb") as f:
        pickle.dump(master_df, f)

    print(f"✅ Success! Optimized file saved to: {output_path}")
    print("🚀 You can now upload this file to your GitHub repository!")

if __name__ == "__main__":
    convert_excel_to_pkl()