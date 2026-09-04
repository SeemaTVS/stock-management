import streamlit as st
import pandas as pd
import re
import requests
import time
import os
import threading
from PIL import Image
import shutil

# --- PDF GENERATION LIBRARIES ---
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import tempfile
import urllib.parse

# Safe Tesseract Setup with fallback
try:
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    else:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except Exception:
    pass

st.set_page_config(
    page_title="TVS Agency Inventory Dashboard", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

st.title("TVS Agency Inventory & Sales Management")

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM/edit?gid=0#gid=0"
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbymkbPavkWPw_5kFEN7S6KQTg2MvS_zqAmGXXkqBAjVDo7XrnUCj9GKKKrA_heBvWZvmQ/exec"

def get_csv_export_url(sheet_url):
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
    if match:
        return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv"
    return sheet_url

CSV_EXPORT_URL = get_csv_export_url(GOOGLE_SHEET_URL)
EXPECTED_COLS = ['part_number', 'description', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold']
SALES_COLS = ['timestamp', 'customer_name', 'items_detail', 'parts_total', 'service_charge', 'discount', 'grand_total', 'total_cost', 'net_profit', 'month_year']

@st.cache_data(ttl=10)
def load_data():
    try:
        cache_buster = int(time.time())
        fresh_url = f"{CSV_EXPORT_URL}&cb={cache_buster}"
        
        df_loaded = pd.read_csv(fresh_url)
        for col in EXPECTED_COLS:
            if col not in df_loaded.columns:
                df_loaded[col] = ""
        
        num_cols = ['unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold']
        for col in num_cols:
            df_loaded[col] = pd.to_numeric(df_loaded[col], errors='coerce').fillna(0)
            
        df_loaded = df_loaded.dropna(subset=['part_number'])
        df_loaded = df_loaded[df_loaded['part_number'].astype(str).str.strip() != ""]
        return df_loaded
    except Exception as e:
        if os.path.exists("inventory_backup.csv"):
            try:
                df_loaded = pd.read_csv("inventory_backup.csv")
                st.warning("⚠️ Network/Google Sheet unreachable. Loaded from local emergency backup file.")
                return df_loaded
            except Exception:
                pass
        st.warning(f"Could not load online Google Sheet, using empty fallback. Details: {e}")
        return pd.DataFrame(columns=EXPECTED_COLS)

def save_data(df_to_save):
    try:
        for col in EXPECTED_COLS:
            if col not in df_to_save.columns:
                df_to_save[col] = ""
        
        num_cols = ['unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold']
        for col in num_cols:
            df_to_save[col] = pd.to_numeric(df_to_save[col], errors='coerce').fillna(0)
            
        df_to_save[num_cols] = df_to_save[num_cols].fillna(0)
        
        text_cols = ['part_number', 'description', 'model']
        for col in text_cols:
            if col in df_to_save.columns:
                df_to_save[col] = df_to_save[col].fillna("").astype(str).str.strip()
            
        df_to_save = df_to_save.dropna(subset=['part_number'])
        df_to_save = df_to_save[df_to_save['part_number'] != ""]

        df_to_save.to_csv("inventory_backup.csv", index=False)

        if WEB_APP_URL:
            with st.spinner("Syncing changes to Google Sheet..."):
                records = df_to_save[EXPECTED_COLS].to_dict(orient="records")
                clean_records = []
                for row in records:
                    clean_row = {}
                    for k, v in row.items():
                        if isinstance(v, float) and (pd.isna(v) or v == float('inf') or v == float('-inf')):
                            clean_row[k] = 0.0
                        else:
                            clean_row[k] = v
                    clean_records.append(clean_row)

                payload = {
                    "type": "inventory",
                    "data": clean_records
                }
                response = requests.post(WEB_APP_URL, json=payload, timeout=10)
                
            if response.status_code == 200:
                st.sidebar.success("Successfully synced!")
            else:
                st.sidebar.error(f"Sync failed: {response.status_code}")
    except Exception as e:
        st.sidebar.error(f"Float/Sync error: {e}")

# --- BACKGROUND AUTOMATIC BACKUP WORKER ---
def background_backup_worker():
    while True:
        time.sleep(3600)  
        try:
            if os.path.exists("inventory_backup.csv"):
                timestamp_name = f"backups/inventory_backup_{time.strftime('%Y%m%d_%H%M%S')}.csv"
                os.makedirs("backups", exist_ok=True)
                shutil.copy("inventory_backup.csv", timestamp_name)
        except Exception:
            pass

if not st.session_state.get('backup_thread_started', False):
    st.session_state['backup_thread_started'] = True
    bg_thread = threading.Thread(target=background_backup_worker, daemon=True)
    bg_thread.start()

def load_sales_log():
    try:
        if WEB_APP_URL:
            response = requests.get(f"{WEB_APP_URL}?action=get_sales", timeout=2, allow_redirects=True)
            if response.status_code == 200:
                sales_data = response.json()
                if isinstance(sales_data, list):
                    sales_df = pd.DataFrame(sales_data)
                    for col in SALES_COLS:
                        if col not in sales_df.columns:
                            sales_df[col] = ""
                    return sales_df
    except Exception:
        pass
    return pd.DataFrame(columns=SALES_COLS)

def save_sale_to_cloud(new_sale_row_dict):
    try:
        if WEB_APP_URL:
            payload = {
                "type": "sale",
                "data": new_sale_row_dict
            }
            requests.post(WEB_APP_URL, json=payload, timeout=10)
    except Exception as e:
        st.error(f"Error saving sale to cloud: {e}")

# --- PDF GENERATOR FUNCTION ---
def generate_invoice_pdf(cust_name, bill_items, subtotal_parts, total_cgst, total_sgst, service_charge, discount, grand_total, transaction_time):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    c = canvas.Canvas(temp_file.name, pagesize=landscape(letter))
    width, height = landscape(letter)
    
    title_color = colors.HexColor("#003366") 
    text_color = colors.black
    
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(title_color)
    c.drawCentredString(width / 2, height - 40, "SEEMA TVS")
    
    c.setFont("Helvetica", 9)
    c.setFillColor(text_color)
    c.drawCentredString(width / 2, height - 55, "Near Hydel Main Road, Sampurna Nagar, Palia Kalan")
    c.drawCentredString(width / 2, height - 68, "Customer Care: 8052751476")
    
    c.setStrokeColor(title_color)
    c.line(40, height - 80, width - 40, height - 80)
    
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, height - 100, f"Customer Name: {cust_name}")
    c.drawRightString(width - 40, height - 100, f"Date: {transaction_time}")
    
    y_table_start = height - 130
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y_table_start, "S.No.")
    c.drawString(80, y_table_start, "Description")
    c.drawString(320, y_table_start, "Qty")
    c.drawString(380, y_table_start, "Base Price (Rs.)")
    c.drawString(490, y_table_start, "CGST 9% (Rs.)")
    c.drawString(600, y_table_start, "SGST 9% (Rs.)")
    c.drawString(710, y_table_start, "Total MRP (Rs.)")
    
    c.setStrokeColor(colors.lightgrey)
    c.line(40, y_table_start - 5, width - 40, y_table_start - 5)
    
    c.setFont("Helvetica", 9)
    y_pos = y_table_start - 20
    for i, item in enumerate(bill_items):
        item_base = item['mrp_total'] / 1.18
        item_cgst = item_base * 0.09
        item_sgst = item_base * 0.09
        
        c.drawString(40, y_pos, str(i + 1))
        desc = item['desc']
        if len(desc) > 45: desc = desc[:42] + "..."
        c.drawString(80, y_pos, desc)
        c.drawString(320, y_pos, str(item['qty']))
        c.drawString(380, y_pos, f"{item_base:.2f}")
        c.drawString(490, y_pos, f"{item_cgst:.2f}")
        c.drawString(600, y_pos, f"{item_sgst:.2f}")
        c.drawString(710, y_pos, f"{item['mrp_total']:.2f}")
        y_pos -= 18
        
    y_totals = y_pos - 15
    c.line(500, y_totals + 12, width - 40, y_totals + 12)
    
    c.setFont("Helvetica", 9)
    if service_charge > 0:
        c.drawString(550, y_totals, "Service Charge:")
        c.drawRightString(width - 40, y_totals, f"Rs. {service_charge:.2f}")
        y_totals -= 14
        
    if discount > 0:
        c.drawString(550, y_totals, "Discount applied:")
        c.drawRightString(width - 40, y_totals, f"-Rs. {discount:.2f}")
        y_totals -= 14
        
    c.setFont("Helvetica-Bold", 10)
    c.drawString(550, y_totals, "GRAND TOTAL:")
    c.drawRightString(width - 40, y_totals, f"Rs. {grand_total:.2f}")
    
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawCentredString(width / 2, 30, "Thank you for your business! Please visit again.")
    
    c.saveState()
    c.setFillAlpha(0.06)
    c.rotate(25)
    c.setFont("Helvetica-Bold", 90)
    c.setFillColor(title_color)
    c.drawString(150, -50, "SEEMA TVS")
    c.restoreState()
    
    c.save()
    temp_file.close()
    return temp_file.name

with st.spinner("Loading application data..."):
    df = load_data()
    sales_df = load_sales_log()

def parse_tvs_label(scanned_text):
    part_no = ""
    description = ""
    mrp_val = 0.0
    
    if not scanned_text:
        return part_no, description, mrp_val
        
    lines = scanned_text.split('\n')
    cleaned_lines = [l.strip() for l in lines if l.strip()]
    
    for line in cleaned_lines:
        line_upper = line.upper()
        
        if not part_no:
            match_pn = re.search(r'\b[A-Z]{1,2}\d{5,7}\b', line_upper)
            if match_pn:
                part_no = match_pn.group(0)
        
        if mrp_val == 0.0 and ("MRP" in line_upper or "RS" in line_upper):
            match_mrp = re.findall(r'(\d+\.\d{2})', line)
            if match_mrp:
                mrp_val = float(match_mrp[-1])
                
        if not description and "PRODUCT" in line_upper:
            cleaned_desc = re.sub(r'PRODUCT[:\s]*', '', line, flags=re.IGNORECASE).strip()
            if len(cleaned_desc) > 2:
                description = cleaned_desc

    if mrp_val == 0.0:
        for line in cleaned_lines:
            match_all_nums = re.findall(r'(\d+\.\d{2})', line)
            if match_all_nums:
                mrp_val = float(match_all_nums[0])
                break

    return part_no, description, mrp_val

# --- DEALER BILL OCR PARSER ---
def parse_dealer_bill(scanned_text):
    parsed_items = []
    if not scanned_text:
        return parsed_items
        
    lines = [l.strip() for l in scanned_text.split('\n') if l.strip()]
    
    # Simple heuristic line parser looking for TVS part numbers and numeric sequences
    for i, line in enumerate(lines):
        line_upper = line.upper()
        match_pn = re.search(r'\b([A-Z0-9]{5,10})\b', line_upper)
        if match_pn and ("/" in line or len(line_upper) <= 12):
            potential_pn = match_pn.group(1)
            # Gather subsequent numbers on current or nearby lines for Qty and initial MRP
            collected_numbers = []
            for j in range(i, min(i + 6, len(lines))):
                nums = re.findall(r'\b\d+(?:\.\d{2})?\b', lines[j])
                for n in nums:
                    collected_numbers.append(float(n))
            
            if len(collected_numbers) >= 2:
                # The first reliable integer or small float near the front is often qty, subsequent is MRP
                qty = int(collected_numbers[0]) if collected_numbers[0] < 1000 else 1
                mrp = collected_numbers[1] if len(collected_numbers) > 1 else 0.0
                if mrp < qty and len(collected_numbers) > 2:
                    mrp = collected_numbers[2]
                
                if potential_pn and mrp > 0:
                    parsed_items.append({
                        "part_number": potential_pn,
                        "qty": qty,
                        "mrp": mrp,
                        "description": f"Auto-imported part {potential_pn}"
                    })
    return parsed_items

# --- SIDEBAR CONTROLS ---
st.sidebar.header("📷 Label Scanner")
uploaded_photo = st.sidebar.file_uploader("Snap/Upload Part Sticker", type=["jpg", "jpeg", "png"])

scanned_part = ""
scanned_desc = ""
scanned_mrp = 0.0

if uploaded_photo:
    try:
        img = Image.open(uploaded_photo)
        ocr_text = pytesseract.image_to_string(img)
        scanned_part, scanned_desc, scanned_mrp = parse_tvs_label(ocr_text)
        if scanned_part:
            st.sidebar.success(f"Detected Part: {scanned_part}")
        else:
            st.sidebar.warning("Could not auto-detect part number.")
    except Exception as e:
        st.sidebar.error(f"Scanner Error: {e}")

st.sidebar.markdown("---")

# --- DEALER BILL SCANNER EXPANDER ---
st.sidebar.header("📋 Dealer Bill Ingestion")
with st.sidebar.expander("📄 Scan Dealer Purchase Bill"):
    uploaded_bill = st.file_uploader("Upload Dealer Bill Invoice", type=["jpg", "jpeg", "png"], key="dealer_bill_upload")
    if uploaded_bill:
        try:
            bill_img = Image.open(uploaded_bill)
            bill_ocr = pytesseract.image_to_string(bill_img)
            extracted_bill_items = parse_dealer_bill(bill_ocr)
            
            if extracted_bill_items:
                st.success(f"Successfully extracted {len(extracted_bill_items)} items from bill!")
                if st.button("Apply Scanned Bill to Inventory"):
                    for item in extracted_bill_items:
                        p_no = item["part_number"].strip().upper()
                        b_qty = item["qty"]
                        b_mrp = item["mrp"]
                        b_cost = round(b_mrp * 0.84, 2)
                        
                        existing_match = df[df['part_number'].astype(str).str.strip().str.upper() == p_no]
                        
                        if not existing_match.empty:
                            # Item exists: update stock qty and MRP, retain existing custom name/description
                            current_qty = int(existing_match.iloc[0]['stock_qty'])
                            new_qty = current_qty + b_qty
                            df.loc[df['part_number'].astype(str).str.strip().str.upper() == p_no, 'stock_qty'] = new_qty
                            df.loc[df['part_number'].astype(str).str.strip().str.upper() == p_no, 'unit_mrp'] = float(b_mrp)
                            df.loc[df['part_number'].astype(str).str.strip().str.upper() == p_no, 'unit_cost'] = float(b_cost)
                        else:
                            # New item: add with extracted details
                            new_row = pd.DataFrame([{
                                'part_number': p_no,
                                'description': item['description'],
                                'model': 'Universal',
                                'unit_cost': float(b_cost),
                                'unit_mrp': float(b_mrp),
                                'stock_qty': int(b_qty),
                                'min_threshold': 5,
                                'units_sold': 0
                            }])
                            df = pd.concat([df, new_row], ignore_index=True)
                    
                    save_data(df)
                    st.success("Dealer bill successfully processed and inventory updated!")
                    time.sleep(1)
                    st.rerun()
            else:
                st.warning("Could not automatically parse items from the bill image. Please check image clarity.")
        except Exception as e:
            st.error(f"Bill Parsing Error: {e}")

st.sidebar.markdown("---")

# --- UNIFIED PART MANAGER ---
st.sidebar.header("📦 Part Manager & Stock Control")

if "lookup_part_input" not in st.session_state:
    st.session_state["lookup_part_input"] = scanned_part

input_part_no = st.sidebar.text_input("Enter/Scan Part Number", value=st.session_state["lookup_part_input"])

matched_row = None
if input_part_no.strip() and not df.empty and 'part_number' in df.columns:
    match_filter = df[df['part_number'].astype(str).str.strip().str.upper() == input_part_no.strip().upper()]
    if not match_filter.empty:
        matched_row = match_filter.iloc[0]

with st.sidebar.form("unified_part_form"):
    if matched_row is not None:
        st.info(f"ℹ️ Found existing part: **{matched_row['part_number']}**")
        val_desc = matched_row['description']
        val_model = matched_row['model']
        val_mrp = float(matched_row['unit_mrp'])
        val_qty = int(matched_row['stock_qty'])
        val_min = int(matched_row['min_threshold'])
        submit_label = "Update Part / Stock"
    else:
        if input_part_no.strip():
            st.warning("⚠️ Part not found. Fill details to add new part.")
        val_desc = scanned_desc
        val_model = "Universal"
        val_mrp = float(scanned_mrp) if scanned_mrp > 0 else 0.0
        val_qty = 0
        val_min = 5
        submit_label = "Add New Part"

    f_desc = st.text_input("Description", value=val_desc)
    f_model = st.text_input("Model", value=val_model)
    f_mrp = st.number_input("Unit MRP (Rs.)", min_value=0.0, value=val_mrp, step=1.0)
    
    f_cost = round(f_mrp * 0.84, 2) if f_mrp > 0 else 0.0
    st.caption(f"Calculated Unit Cost (MRP - 16%): Rs. {f_cost}")

    f_qty = st.number_input("Stock Quantity", min_value=0, value=val_qty, step=1)
    f_min = st.number_input("Min Threshold", min_value=1, value=val_min, step=1)

    submitted = st.form_submit_button(submit_label)

    if submitted:
        clean_pn = input_part_no.strip()
        if not clean_pn:
            st.error("Part Number cannot be empty!")
        else:
            if matched_row is not None:
                df.loc[df['part_number'].astype(str).str.strip().str.upper() == clean_pn.upper(), 'description'] = f_desc.strip()
                df.loc[df['part_number'].astype(str).str.strip().str.upper() == clean_pn.upper(), 'model'] = f_model.strip()
                df.loc[df['part_number'].astype(str).str.strip().str.upper() == clean_pn.upper(), 'unit_mrp'] = float(f_mrp)
                df.loc[df['part_number'].astype(str).str.strip().str.upper() == clean_pn.upper(), 'unit_cost'] = float(f_cost)
                df.loc[df['part_number'].astype(str).str.strip().str.upper() == clean_pn.upper(), 'stock_qty'] = int(f_qty)
                df.loc[df['part_number'].astype(str).str.strip().str.upper() == clean_pn.upper(), 'min_threshold'] = int(f_min)
                st.success(f"Successfully updated part {clean_pn}!")
            else:
                new_row = pd.DataFrame([{
                    'part_number': clean_pn,
                    'description': f_desc.strip(),
                    'model': f_model.strip(),
                    'unit_cost': float(f_cost),
                    'unit_mrp': float(f_mrp),
                    'stock_qty': int(f_qty),
                    'min_threshold': int(f_min),
                    'units_sold': 0
                }])
                df = pd.concat([df, new_row], ignore_index=T)
