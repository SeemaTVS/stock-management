import streamlit as st
import pandas as pd
import re
import os
from PIL import Image
import pytesseract
import shutil

# Automatically find Tesseract whether running on Windows or Streamlit Cloud
tesseract_path = shutil.which("tesseract")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(
    page_title="TVS Agency Inventory Dashboard", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.title("TVS Agency Inventory & Order Management")

# Your connected Google Sheet link
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM/edit?gid=0#gid=0"

def get_csv_export_url(sheet_url):
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
    if match:
        sheet_id = match.group(1)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    return sheet_url

CSV_EXPORT_URL = get_csv_export_url(GOOGLE_SHEET_URL)

# 1. Load Data from Google Sheets
def load_data():
    try:
        df_loaded = pd.read_csv(CSV_EXPORT_URL)
        for col_to_drop in ['category', 'max_capacity']:
            if col_to_drop in df_loaded.columns:
                df_loaded = df_loaded.drop(columns=[col_to_drop])
        if 'units_sold' not in df_loaded.columns:
            df_loaded['units_sold'] = 0
        return df_loaded
    except Exception as e:
        st.error(f"Could not load from Google Sheet. Make sure the link is public (Anyone with the link can view/edit). Error: {e}")
        return pd.DataFrame(columns=[
            'part_number', 'description', 'model', 
            'unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold'
        ])

def save_data(df_to_save):
    st.success("Changes processed locally! Download the backup file below to paste straight into your Google Sheet if needed.")

df = load_data()

# 2. TVS Barcode/QR Text Cleaner
def extract_part_number(scanned_text):
    if not scanned_text:
        return None
    cleaned = str(scanned_text).strip()
    if "|" in cleaned:
        parts = cleaned.split("|")
        for part in parts:
            if re.match(r'^[A-Z0-9]{5,10}$', part.strip()):
                return part.strip()
    
    matches = re.findall(r'[A-Z0-9]{5,10}', cleaned)
    if matches:
        return matches[0]
        
    return cleaned

# --- SIDEBAR CONTROLS ---

st.sidebar.header("📷 Snap Label Photo")
uploaded_photo = st.sidebar.file_uploader("Take Photo of Label", type=["jpg", "jpeg", "png"])

scanned_input = ""
if uploaded_photo:
    try:
        img = Image.open(uploaded_photo)
        extracted_text = pytesseract.image_to_string(img)
        scanned_input = extract_part_number(extracted_text)
        if not scanned_input:
            st.sidebar.warning("Image read, but no TVS part code pattern found.")
    except Exception as e:
        st.sidebar.error(f"OCR System Error: {e}")

manual_input = st.sidebar.text_input("Or type Part # manually:", value=scanned_input if scanned_input else "")

active_part = manual_input if manual_input else scanned_input
default_new_part = ""

if active_part:
    st.sidebar.info(f"Detected Part: **{active_part}**")
    
    if not df.empty and active_part in df['part_number'].values:
        if st.sidebar.button("Add +1 to Stock"):
            df.loc[df['part_number'] == active_part, 'stock_qty'] += 1
            save_data(df)
            st.rerun()
    else:
        st.sidebar.warning(f"Part '{active_part}' not found in database.")
        default_new_part = active_part

st.sidebar.markdown("---")

st.sidebar.header("⚙️ Manual Stock Adjustment")
selected_part = st.sidebar.selectbox("Select Part to Update", df['part_number'].unique() if not df.empty else [])
if selected_part:
    qty_change = st.sidebar.number_input("Quantity Change (+ or -)", value=1, step=1)
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("Add Stock"):
            df.loc[df['part_number'] == selected_part, 'stock_qty'] += qty_change
            save_data(df)
            st.rerun()
    with col2:
        if st.button("Record Sale"):
            current_stock = df.loc[df['part_number'] == selected_part, 'stock_qty'].values[0]
            if current_stock >= qty_change:
                df.loc[df['part_number'] == selected_part, 'stock_qty'] -= qty_change
                df.loc[df['part_number'] == selected_part, 'units_sold'] += qty_change
                save_data(df)
                st.rerun()
            else:
                st.error("Insufficient stock!")

st.sidebar.markdown("---")

st.sidebar.header("➕ Add New Part to Inventory")
with st.sidebar.form("add_part_form", clear_on_submit=True):
    new_part_no = st.text_input("Part Number", value=default_new_part)
    new_desc = st.text_input("Description (e.g., Brake Shoe / Oil Seal)")
    new_model = st.text_input("Model / Compatibility", value="Universal")
    new_cost = st.number_input("Unit Cost (₹)", min_value=0.0, value=0.0, step=1.0)
    new_mrp = st.number_input("Unit MRP (₹)", min_value=0.0, value=0.0, step=1.0)
    new_qty = st.number_input("Initial Stock Quantity", min_value=0, value=1, step=1)
    new_min = st.number_input("Min Threshold (Reorder Level)", min_value=1, value=5, step=1)
    
    submit_new_part = st.form_submit_button("Add Part to Database")
    
    if submit_new_part:
        if not new_part_no:
            st.sidebar.error("Part Number is required!")
        elif not df.empty and new_part_no in df['part_number'].values:
            st.sidebar.error("Part Number already exists!")
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

    st.sidebar.markdown("---")
    st.sidebar.header("📥 Sync with Google Sheet")
    csv_bytes = df.drop(columns=['status'], errors='ignore').to_csv(index=False).encode('utf-8')
    st.sidebar.download_button(
        label="Download Sheet Backup CSV",
        data=csv_bytes,
        file_name="inventory.csv",
        mime="text/csv",
        help="Download this and paste it directly into your Google Sheet columns."
    )

    tab1, tab2, tab3 = st.tabs(["📊 Overview & Stock", "✏️ Edit Inventory Data", "🚨 Reorder Alerts"])

    with tab1:
        st.subheader("Current Stock Inventory")
        st.dataframe(df[['part_number', 'description', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'units_sold', 'status']], use_container_width=True)

    with tab2:
        st.subheader("Interactive Master Data Editor")
        edited_df = st.data_editor(df.drop(columns=['status'], errors='ignore'), num_rows="dynamic", key="editor")
        if st.button("Save Changes"):
            save_data(edited_df)
            st.rerun()

    with tab3:
        st.subheader("Stock Requiring Attention")
        low_stock = df[df['status'].isin(["OUT OF STOCK", "REORDER NEEDED"])]
        if not low_stock.empty:
            st.warning(f"Found {len(low_stock)} items that need restocking!")
            st.dataframe(low_stock[['part_number', 'description', 'stock_qty', 'min_threshold', 'status']], use_container_width=True)
        else:
            st.success("All inventory levels are healthy!")
else:
    st.info("Waiting for data to load from your Google Sheet link...")
