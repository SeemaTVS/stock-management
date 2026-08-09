import streamlit as st
import pandas as pd
import re
import requests
import io

st.set_page_config(page_title="TVS Agency Inventory Dashboard", layout="wide")

st.title("TVS Agency Inventory & Order Management")

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM/edit?gid=0#gid=0"
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbymkbPavkWPw_5kFEN7S6KQTg2MvS_zqAmGXXkqBAjVDo7XrnUCj9GKKKrA_heBvWZvmQ/exec"

def get_csv_export_url(sheet_url):
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
    if match:
        return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv"
    return sheet_url

CSV_EXPORT_URL = get_csv_export_url(GOOGLE_SHEET_URL)
EXPECTED_COLS = ['part_number', 'description', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold']

def load_data():
    try:
        df_loaded = pd.read_csv(CSV_EXPORT_URL)
        for col in EXPECTED_COLS:
            if col not in df_loaded.columns:
                df_loaded[col] = ""
        if 'units_sold' not in df_loaded.columns:
            df_loaded['units_sold'] = 0
        return df_loaded.dropna(subset=['part_number'])
    except Exception as e:
        st.error(f"Load error: {e}")
        return pd.DataFrame(columns=EXPECTED_COLS)

def save_data(df_to_save):
    try:
        data_dict = df_to_save[EXPECTED_COLS].to_dict(orient="records")
        response = requests.post(WEB_APP_URL, json=data_dict, timeout=10)
        st.success("Synced successfully to Google Sheet!")
    except Exception as e:
        st.error(f"Sync failed: {e}")

df = load_data()

if not df.empty:
    st.subheader("Inventory Master Editor")
    edited_df = st.data_editor(df, num_rows="dynamic", key="main_editor")
    if st.button("Save Changes"):
        save_data(edited_df)
        st.rerun()
else:
    st.warning("Database is empty.")
