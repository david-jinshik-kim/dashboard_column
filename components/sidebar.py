import streamlit as st
import pandas as pd

def render_sidebar_filters(df):
    st.sidebar.markdown("---")
    st.sidebar.header("Dashboard Filters")

    if 'grp_count' not in st.session_state: st.session_state.grp_count = 0
    if 'sty_count' not in st.session_state: st.session_state.sty_count = 0
    if 'cas_count' not in st.session_state: st.session_state.cas_count = 0

    def bump_grp(): st.session_state.grp_count += 1
    def bump_sty(): st.session_state.sty_count += 1
    def bump_cas(): st.session_state.cas_count += 1

    # Groups
    all_groups_list = sorted(list(set(g for g_str in df['Group Name'].dropna() for g in g_str.split(', '))))
    group_search = st.sidebar.text_input("🔍 Search Groups:", key="search_groups")
    filtered_groups_list = [g for g in all_groups_list if group_search.lower() in g.lower()] if group_search else all_groups_list
    all_groups_chk = st.sidebar.checkbox(f"Select All ({len(filtered_groups_list)} Matches)", value=True, key="chk_groups", on_change=bump_grp)
    group_ms_key = f"ms_groups_{group_search}_{st.session_state.grp_count}"
    selected_groups = st.sidebar.multiselect("Select Group Name(s):", options=filtered_groups_list, default=filtered_groups_list if all_groups_chk else filtered_groups_list[:1], key=group_ms_key)

    # Stories
    stories_list = sorted(df['Story'].dropna().unique().tolist())
    story_search = st.sidebar.text_input("🔍 Search Stories:", key="search_stories")
    filtered_stories_list = [s for s in stories_list if story_search.lower() in s.lower()] if story_search else stories_list
    all_stories_chk = st.sidebar.checkbox(f"Select All ({len(filtered_stories_list)} Matches)", value=True, key="chk_stories", on_change=bump_sty)
    story_ms_key = f"ms_stories_{story_search}_{st.session_state.sty_count}"
    selected_stories = st.sidebar.multiselect("Select Story(ies):", options=filtered_stories_list, default=filtered_stories_list if all_stories_chk else filtered_stories_list[:1], key=story_ms_key)

    # Cases
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
    
    return df[mask].copy()