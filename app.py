import streamlit as st
import pandas as pd
import re
import requests
import io

st.set_page_config(
    page_title="TVS Agency Inventory Dashboard", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

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
    for col in EXPECTED_COLS:
        if col not in df_to_save.columns:
            df_to_save[col] = 0
            
    if WEB_APP_URL:
        try:
            with st.spinner("Syncing changes..."):
                data_dict = df_to_save[EXPECTED_COLS].to_dict(orient="records")
                response = requests.post(WEB_APP_URL, json=data_dict, timeout=15)
                
            if response.status_code == 200:
                st.sidebar.success("Successfully synced to Google Sheet!")
            else:
                st.sidebar.error(f"Sync failed with status: {response.status_code}")
        except Exception as e:
            st.sidebar.error(f"Sync error: {e}")

df = load_data()

# --- SIDEBAR CONTROLS ---
st.sidebar.header("⚙️ Manual Stock Adjustment")
if not df.empty and 'part_number' in df.columns:
    part_options = df['part_number'].unique()
    selected_part = st.sidebar.selectbox("Select Part to Update", part_options)

    if selected_part:
        qty_change = st.sidebar.number_input("Quantity Change (+ or -)", value=1, step=1)
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.sidebar.button("Add Stock"):
                df.loc[df['part_number'] == selected_part, 'stock_qty'] += qty_change
                save_data(df)
                st.rerun()
        with col2:
            if st.sidebar.button("Record Sale"):
                current_stock = df.loc[df['part_number'] == selected_part, 'stock_qty'].values[0]
                if current_stock >= qty_change:
                    df.loc[df['part_number'] == selected_part, 'stock_qty'] -= qty_change
                    df.loc[df['part_number'] == selected_part, 'units_sold'] += qty_change
                    save_data(df)
                    st.rerun()
                else:
                    st.sidebar.error("Insufficient stock!")

st.sidebar.markdown("---")
st.sidebar.header("➕ Add New Part")
with st.sidebar.form("add_part_form", clear_on_submit=True):
    new_part_no = st.text_input("Part Number")
    new_desc = st.text_input("Description")
    new_model = st.text_input("Model", value="Universal")
    new_cost = st.number_input("Unit Cost (₹)", min_value=0.0, value=0.0)
    new_mrp = st.number_input("Unit MRP (₹)", min_value=0.0, value=0.0)
    new_qty = st.number_input("Initial Stock", min_value=0, value=1)
    new_min = st.number_input("Min Threshold", min_value=1, value=5)
    
    submit_new_part = st.form_submit_button("Add to Database")
    
    if submit_new_part:
        if not new_part_no:
            st.sidebar.error("Part Number is required!")
        else:
            new_row = pd.DataFrame([{
                'part_number': new_part_no.strip(),
                'description': new_desc.strip(),
                'model': new_model.strip(),
                'unit_cost': new_cost,
                'unit_mrp': new_mrp,
                'stock_qty': new_qty,
                'min_threshold': new_min,
                'units_sold': 0
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.rerun()

# --- MAIN DASHBOARD TABS ---
if not df.empty:
    def calculate_status(row):
        if row['stock_qty'] == 0:
            return "OUT OF STOCK"
        elif row['stock_qty'] <= row['min_threshold']:
            return "REORDER NEEDED"
        else:
            return "IN STOCK"

    df['status'] = df.apply(calculate_status, axis=1)

    tab1, tab2 = st.tabs(["📊 Overview & Stock", "✏️ Edit Master Data"])

    with tab1:
        st.subheader("Current Stock Inventory")
        st.dataframe(df[['part_number', 'description', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'units_sold', 'status']], use_container_width=True)

    with tab2:
        st.subheader("Interactive Master Data Editor")
        edited_df = st.data_editor(df.drop(columns=['status'], errors='ignore'), num_rows="dynamic", key="editor")
        if st.button("Save Changes to Google Sheet"):
            save_data(edited_df)
            st.rerun()
else:
    st.info("Your inventory database is currently empty.")
