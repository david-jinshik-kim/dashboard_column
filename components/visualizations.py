import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

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

def render_charts(filtered_df, force_configs):
    st.markdown("---")
    st.subheader("Element Forces - 3D Views, Bar Charts, and Box Plots")

    all_unique_stories = filtered_df['Story'].dropna().unique()
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
    for _, group in filtered_df.groupby('Unique Name'):
        if pd.notna(group['Xi'].iloc[0]):
            bg_x.extend([group['Xi'].iloc[0], group['Xj'].iloc[0], None])
            bg_y.extend([group['Yi'].iloc[0], group['Yj'].iloc[0], None])
            bg_z.extend([group['Zi'].iloc[0], group['Zj'].iloc[0], None])

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
            c_min_val, c_max_val = x_min, x_max
        else:
            c_min_val = overall_min if not plot_df.empty else 0.0
            c_max_val = overall_max if not plot_df.empty else 0.0

        shared_colorbar = dict(title="Force", thickness=15, lenmode='pixels', len=400, y=0.5, yanchor='middle')

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

            trace_bg = go.Scatter3d(x=bg_x, y=bg_y, z=bg_z, mode='lines', line=dict(color='gray', width=0.5), hoverinfo='none', showlegend=False)
            trace_fg = go.Scatter3d(x=x_lines, y=y_lines, z=z_lines, mode='lines', line=dict(color=c_lines, colorscale=c_scale, cmin=c_min_val, cmax=c_max_val, width=6, colorbar=shared_colorbar), text=text_lines, hoverinfo='text', showlegend=False)
            
            fig_3d = go.Figure(data=[trace_bg, trace_fg])
            fig_3d.update_layout(title_text=fig3d_title, title_x=0.0, scene=dict(aspectmode='data', camera=dict(eye=dict(x=2.5, y=2.5, z=2.5))), margin=dict(l=0, r=0, b=0, t=80), height=600)
            st.plotly_chart(fig_3d, use_container_width=True)

        with col_plot2:
            fig_bar = px.bar(plot_df, x=col_str, y="Story_Label", orientation='h', color=col_str, color_continuous_scale=c_scale, range_color=[c_min_val, c_max_val])
            fig_bar.update_layout(title_text=bar_title, title_x=0.0, margin=dict(l=0, r=0, b=0, t=80), height=600, coloraxis_colorbar=shared_colorbar)
            fig_bar.update_yaxes(type='category', categoryorder='array', categoryarray=master_story_labels, range=[-0.5, len(master_story_labels) - 0.5])
            if use_custom: fig_bar.update_xaxes(range=[x_min, x_max])
            st.plotly_chart(fig_bar, use_container_width=True)

        box_df = plot_df.copy()
        box_df['Element Force'] = col_str 
        fig_box = px.box(box_df, x=col_str, y='Element Force', orientation='h', points="all")
        fig_box.update_layout(title_text=box_title, title_x=0.0, margin=dict(t=80))
        fig_box.update_traces(pointpos=0, jitter=0.2)
        if use_custom: fig_box.update_xaxes(range=[x_min, x_max])
        st.plotly_chart(fig_box, use_container_width=True)
        st.markdown("---")