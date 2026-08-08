import streamlit as st
import pandas as pd
import re
import os
from PIL import Image
import pytesseract
import shutil

# Try importing pyzbar for QR/Barcode scanning
try:
    from pyzbar.pyzbar import decode
    PYZBAR_AVAILABLE = True
except Exception:
    PYZBAR_AVAILABLE = False

# Automatically find Tesseract whether running on Windows or Streamlit Cloud
tesseract_path = shutil.which("tesseract")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    # Fallback to default Windows path if running locally
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.title("TVS Agency Inventory & Order Management")

# 1. Load Data from Google Sheets
def load_data():
  conn = st.connection("gsheets", type="gsheets")
df_loaded = conn.read(
    spreadsheet="https://docs.google.com/spreadsheets/d/1Ri014cRyCS2I-IODe-9D2zp4bZ4aSUg_d84vWx5uENs/edit?gid=0#gid=0",
    ttl=0
    )
if 'units_sold' not in df_loaded.columns:
        df_loaded['units_sold'] = 0
return df_loaded

import gspread
from google.oauth2.service_account import Credentials

def save_data(df_to_save):
    base_cols = ['part_number', 'description', 'category', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'max_capacity', 'units_sold']
    for col in base_cols:
        if col not in df_to_save.columns:
            df_to_save[col] = 0
            
    # Fallback to grab whatever dictionary configuration exists in secrets
    try:
        creds_dict = dict(st.secrets["connections"]["gsheets"])
    except Exception:
        try:
            creds_dict = dict(st.secrets["gsheets"])
        except Exception:
            creds_dict = dict(st.secrets)
            
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1Ri014cRyCS2I-IODe-9D2zp4bZ4aSUg_d84vWx5uENs/edit?gid=0#gid=0")
    worksheet = sheet.get_worksheet(0)
    worksheet.clear()
    df_to_save.to_csv("inventory.csv", index=False)
    worksheet.update([df_to_save.columns.values.tolist()] + df_to_save.values.tolist())
df = load_data()
# 2. TVS Barcode/QR & OCR Extractor
def extract_label_data(img_obj):
    # STEP A: Try Barcode / QR Code first
    if PYZBAR_AVAILABLE:
        try:
            barcodes = decode(img_obj)
            for barcode in barcodes:
                data = barcode.data.decode('utf-8').strip()
                if "|" in data:
                    for part in data.split("|"):
                        cleaned_part = re.sub(r'[^A-Z0-9]', '', part.strip().upper())
                        if len(cleaned_part) >= 5:
                            return cleaned_part, "", 0.0
                else:
                    cleaned_data = re.sub(r'[^A-Z0-9]', '', data.upper())
                    if len(cleaned_data) >= 5:
                        return cleaned_data, "", 0.0
        except Exception:
            pass

    # STEP B: OCR Text Recognition Fallback
    scanned_text = pytesseract.image_to_string(img_obj)
    if not scanned_text:
        return None, "", 0.0

    cleaned = str(scanned_text).strip()
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    print("--- OCR RAW TEXT START ---")
    print(cleaned)
    print("--- OCR RAW TEXT END ---")
    extracted_part = None
    extracted_desc = ""
    extracted_mrp = 0.0

    ignore_words = [
        "FREE", "TOLL", "CALL", "MAIL", "INDIA", "TVSMOTOR", "HOSUR",
        "CUSTOMER", "EXECUTIVE", "COMPANY", "LIMITED", "NUMBER", "QUANTITY",
        "PRODUCT", "TAXES", "MANUFAC", "MANUFACTURED", "ADDRESS", "COMPLAINTS",
        "SOSTS2", "GENUINE", "PARTS"
    ]

  # 1. Part Number (Global Search)
    extracted_part = None
    
    matches = re.findall(r'\b([A-Z]{1,2}\d{7})\b', cleaned.upper())
    if matches:
        for m in matches:
            if m not in ignore_words and "635109" not in m:
                extracted_part = m
                break
                
    if not extracted_part:
        num_matches = re.findall(r'\b(\d{7,8})\b', cleaned)
        for m in num_matches:
            if m != "635109" and m != "1800258":
                extracted_part = m
                break
   # 2. Product Description
    for line in lines:
        if "PRODUCT:" in line.upper():
            extracted_desc = line.upper().split("PRODUCT:")[1].strip()
            break

    # 3. MRP
    mrp_match = re.search(r'MRP\s*(?:RS\.?|INR|\₹)?\s*([0-9]+(?:\.[0-9]{1,2})?)', cleaned, re.IGNORECASE)
    if mrp_match:
        try:
            extracted_mrp = float(mrp_match.group(1))
        except ValueError:
            extracted_mrp = 0.0

    return extracted_part, extracted_desc, extracted_mrp
# --- SIDEBAR CONTROLS ---

# Section A: Snap Label Photo
st.sidebar.header("📷 Snap Label Photo")
uploaded_photo = st.sidebar.file_uploader("Take Photo of Label", type=["jpg", "jpeg", "png"])

scanned_input = ""
auto_desc = ""
auto_mrp = 0.0

if uploaded_photo:
    try:
        img = Image.open(uploaded_photo)
        img.thumbnail((1000, 1000))
        scanned_input, auto_desc, auto_mrp = extract_label_data(img)      
        if not scanned_input:
            st.sidebar.warning("Image read, but no TVS part code found.")
    except Exception as e:
        st.sidebar.error(f"OCR Error: {e}")

manual_input = st.sidebar.text_input("Or type Part # manually:", value=scanned_input if scanned_input else "")
active_part = manual_input if manual_input else scanned_input

default_new_part = ""

if active_part:
    st.sidebar.info(f"Detected Part: **{active_part}**")
    if active_part in df['part_number'].values:
        if st.sidebar.button("Add +1 to Stock"):
            df.loc[df['part_number'] == active_part, 'stock_qty'] += 1
            save_data(df)
            st.sidebar.success(f"Stock updated for {active_part}!")
            st.rerun()
    else:
        st.sidebar.warning(f"Part '{active_part}' not found in database.")
        default_new_part = active_part

st.sidebar.markdown("---")

# Section B: Manual Stock Adjustment
st.sidebar.header("⚙️ Manual Stock Adjustment")
selected_part = st.sidebar.selectbox("Select Part to Update", df['part_number'].unique() if not df.empty else [])
if selected_part:
    qty_change = st.sidebar.number_input("Quantity Change (+ or -)", value=1, step=1)
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("Add Stock"):
            df.loc[df['part_number'] == selected_part, 'stock_qty'] += qty_change
            save_data(df)
            st.success(f"Added {qty_change} to {selected_part}")
            st.rerun()
    with col2:
        if st.button("Record Sale"):
            current_stock = df.loc[df['part_number'] == selected_part, 'stock_qty'].values[0]
            if current_stock >= qty_change:
                df.loc[df['part_number'] == selected_part, 'stock_qty'] -= qty_change
                df.loc[df['part_number'] == selected_part, 'units_sold'] += qty_change
                save_data(df)
                st.success(f"Sold {qty_change} of {selected_part}")
                st.rerun()
            else:
                st.error("Insufficient stock!")

st.sidebar.markdown("---")

# Section C: Add New Part Form
st.sidebar.header("➕ Add New Part to Inventory")
with st.sidebar.form("add_part_form", clear_on_submit=True):
    new_part_no = st.text_input("Part Number", value=default_new_part)
    new_desc = st.text_input("Description", value=auto_desc if auto_desc else "Spare Part")
    new_cat = st.text_input("Category", value="Spare Parts")
    new_model = st.text_input("Model / Compatibility", value="Universal")
    new_cost = st.number_input("Unit Cost (₹)", min_value=0.0, value=0.0, step=1.0)
    new_mrp = st.number_input("Unit MRP (₹)", min_value=0.0, value=auto_mrp, step=1.0)
    new_qty = st.number_input("Initial Stock Quantity", min_value=0, value=1, step=1)
    new_min = st.number_input("Min Threshold", min_value=1, value=5, step=1)
    new_max = st.number_input("Max Capacity", min_value=1, value=50, step=1)

    submit_new_part = st.form_submit_button("Add Part to Database")

    if submit_new_part:
        if not new_part_no:
            st.sidebar.error("Part Number is required!")
        elif new_part_no in df['part_number'].values:
            st.sidebar.error("Part Number already exists!")
        else:
            new_row = pd.DataFrame([{
                'part_number': new_part_no.strip(),
                'description': new_desc.strip(),
                'category': new_cat.strip(),
                'model': new_model.strip(),
                'unit_cost': new_cost,
                'unit_mrp': new_mrp,
                'stock_qty': new_qty,
                'min_threshold': new_min,
                'max_capacity': new_max,
                'units_sold': 0
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.sidebar.success(f"Added {new_part_no} to inventory!")
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

    tab1, tab2, tab3 = st.tabs(["📊 Overview & Stock", "✏️ Edit Inventory Data", "🚨 Reorder Alerts"])

    with tab1:
        st.subheader("Current Stock Inventory")
        categories = ["All"] + list(df['category'].unique())
        selected_cat = st.selectbox("Filter by Category", categories)

        display_df = df if selected_cat == "All" else df[df['category'] == selected_cat]
        st.dataframe(display_df[['part_number', 'description', 'category', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'units_sold']], height=500)

    with tab2:
        st.subheader("Interactive Master Data Editor")
        st.caption("You can edit values directly in the table below and click Save.")
        edited_df = st.data_editor(df, num_rows="dynamic", key="editor", height=500)
        if st.button("Save Changes to CSV"):
            save_data(edited_df)
            st.success("Database updated successfully!")
            st.rerun()

    with tab3:
        st.subheader("Stock Requiring Attention")
        low_stock = df[df['status'].isin(["OUT OF STOCK", "REORDER NEEDED"])]
        if not low_stock.empty:
            st.warning(f"Found {len(low_stock)} items that need restocking!")
            st.dataframe(low_stock[['part_number', 'description', 'stock_qty', 'min_threshold', 'status']], use_container_width=True)
        else:
            st.success("All inventory levels are healthy!")
