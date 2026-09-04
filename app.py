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

@st.cache_data(ttl=5)
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
        if not df_loaded.empty:
            return df_loaded
    except Exception:
        pass

    # Fallback to local backup if online fetch fails
    if os.path.exists("inventory_backup.csv"):
        try:
            df_loaded = pd.read_csv("inventory_backup.csv")
            for col in EXPECTED_COLS:
                if col not in df_loaded.columns:
                    df_loaded[col] = ""
            num_cols = ['unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold']
            for col in num_cols:
                df_loaded[col] = pd.to_numeric(df_loaded[col], errors='coerce').fillna(0)
            st.warning("⚠️ Loaded inventory from local backup file.")
            return df_loaded
        except Exception:
            pass

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
                response = requests.post(WEB_APP_URL, json=payload, timeout=15)
                
            if response.status_code == 200:
                st.sidebar.success("Successfully synced!")
            else:
                st.sidebar.error(f"Sync failed: {response.status_code}")
    except Exception as e:
        st.sidebar.error(f"Sync error: {e}")

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
            response = requests.get(f"{WEB_APP_URL}?action=get_sales", timeout=5, allow_redirects=True)
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
            requests.post(WEB_APP_URL, json=payload, timeout=15)
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
    
    for i, line in enumerate(lines):
        line_upper = line.upper()
        match_pn = re.search(r'\b([A-Z0-9]{5,10})\b', line_upper)
        if match_pn and ("/" in line or len(line_upper) <= 12):
            potential_pn = match_pn.group(1)
            collected_numbers = []
            for j in range(i, min(i + 6, len(lines))):
                nums = re.findall(r'\b\d+(?:\.\d{2})?\b', lines[j])
                for n in nums:
                    collected_numbers.append(float(n))
            
            if len(collected_numbers) >= 2:
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
                            current_qty = int(existing_match.iloc[0]['stock_qty'])
                            new_qty = current_qty + b_qty
                            df.loc[df['part_number'].astype(str).str.strip().str.upper() == p_no, 'stock_qty'] = new_qty
                            df.loc[df['part_number'].astype(str).str.strip().str.upper() == p_no, 'unit_mrp'] = float(b_mrp)
                            df.loc[df['part_number'].astype(str).str.strip().str.upper() == p_no, 'unit_cost'] = float(b_cost)
                        else:
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
                df = pd.concat([df, new_row], ignore_index=True)
                st.success(f"Successfully added new part {clean_pn}!")
            
            save_data(df)
            time.sleep(1)
            st.rerun()

st.sidebar.markdown("---")

# --- MAIN DASHBOARD TABS ---
if df.empty:
    st.warning("⚠️ Inventory dataset is currently empty. Use the sidebar on the left to add your first part number or check your Google Sheet export URL connection.")
else:
    def calculate_status(row):
        if row['stock_qty'] == 0:
            return "OUT OF STOCK"
        elif row['stock_qty'] <= row['min_threshold']:
            return "REORDER NEEDED"
        else:
            return "IN STOCK"

    df['status'] = df.apply(calculate_status, axis=1)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Overview & Stock", 
        "✏️ Edit Master Data", 
        "🛒 Record Sale",
        "📈 Sales & Profit Reports"
    ])

    with tab1:
        st.subheader("Current Stock Inventory")
        st.dataframe(df[['part_number', 'description', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'units_sold', 'status']], use_container_width=True)

    with tab2:
        st.subheader("Interactive Master Data Editor")
        st.caption("You can freely edit item details and customize unit costs here, or perform bulk deletion of obsolete parts.")
        
        editor_input_df = df.drop(columns=['status'], errors='ignore')
        edited_df = st.data_editor(editor_input_df, num_rows="dynamic", key="editor")
        
        col_save_editor, col_bulk_del = st.columns([1, 1])
        with col_save_editor:
            if st.button("Save Changes to Google Sheet"):
                try:
                    for col in EXPECTED_COLS:
                        if col not in edited_df.columns:
                            edited_df[col] = ""
                    
                    num_cols = ['unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold']
                    for col in num_cols:
                        edited_df[col] = pd.to_numeric(edited_df[col], errors='coerce').fillna(0)
                        
                    edited_df['part_number'] = edited_df['part_number'].astype(str).str.strip()
                    edited_df = edited_df.dropna(subset=['part_number'])
                    edited_df = edited_df[edited_df['part_number'] != ""]
                    
                    save_data(edited_df)
                    st.success("Master data changes successfully saved and synced!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving master data: {e}")
                
        st.markdown("---")
        st.subheader("🗑️ Bulk Delete Obsolete Parts")
        parts_to_delete = st.multiselect("Select Part Numbers to Delete in Batch", df['part_number'].tolist(), key="bulk_delete_select")
        if st.button("Delete Selected Parts", type="primary"):
            if parts_to_delete:
                df = df[~df['part_number'].isin(parts_to_delete)]
                save_data(df)
                st.success(f"Successfully deleted {len(parts_to_delete)} parts!")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Please select at least one part number to delete.")

    with tab3:
        st.subheader("Record New Sale Transaction")
        st.caption("Select sold items, enter customer WhatsApp number side-by-side, and complete checkout to generate the invoice.")
        
        cust_name = st.text_input("Customer / Reference Name", value="Walk-in Customer")
        
        st.markdown("### 📱 Customer WhatsApp Number")
        col_cc, col_num = st.columns([1, 4])
        with col_cc:
            country_code = st.text_input("Code", value="91")
        with col_num:
            cust_phone_10 = st.text_input("10-Digit WhatsApp Number", max_chars=10, placeholder="e.g. 6380965289")

        selected_billing_parts = st.multiselect("Select Parts Sold", df['part_number'].tolist(), key="sale_parts_select")
        
        bill_items = []
        parts_mrp_total = 0.0
        parts_cost_total = 0.0
        
        if selected_billing_parts:
            st.markdown("### Sold Quantities")
            for part in selected_billing_parts:
                row_data = df[df['part_number'] == part].iloc[0]
                desc = row_data['description']
                mrp = float(row_data['unit_mrp'])
                cost = float(row_data['unit_cost'])
                avail_qty = int(row_data['stock_qty'])
                
                col_q1, col_q2 = st.columns([3, 1])
                with col_q1:
                    st.write(f"**{desc}** (MRP: Rs. {mrp}) | Stock: {avail_qty}")
                with col_q2:
                    qty_sold = st.number_input(f"Qty [{part}]", min_value=1, max_value=max(1, avail_qty), value=1, key=f"sale_qty_{part}")
                
                item_mrp_sum = mrp * qty_sold
                item_cost_sum = cost * qty_sold
                parts_mrp_total += item_mrp_sum
                parts_cost_total += item_cost_sum
                bill_items.append({
                    "part": part, 
                    "desc": desc, 
                    "qty": qty_sold, 
                    "mrp": mrp, 
                    "cost": cost,
                    "mrp_total": item_mrp_sum,
                    "cost_total": item_cost_sum
                })
            
            st.markdown("---")
            col_add1, col_add2 = st.columns(2)
            with col_add1:
                service_charge = st.number_input("Service / Labor Charge (Rs.)", min_value=0.0, value=0.0, step=10.0)
            with col_add2:
                discount_val = st.number_input("Discount (Rs.)", min_value=0.0, value=0.0, step=10.0)
                
            final_grand_total = max(0.0, parts_mrp_total + service_charge - discount_val)
            expected_net_profit = final_grand_total - parts_cost_total
            
            taxable_base_total = parts_mrp_total / 1.18
            total_cgst = taxable_base_total * 0.09
            total_sgst = taxable_base_total * 0.09
            
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                st.metric("Parts Total (MRP)", f"Rs. {parts_mrp_total:.2f}")
            with col_p2:
                st.metric("Grand Total (Sale Price)", f"Rs. {final_grand_total:.2f}")
            with col_p3:
                st.metric("Net Profit", f"Rs. {expected_net_profit:.2f}")
            
            if st.button("Complete Checkout & Generate Bill PDF", type="primary"):
                sale_success = True
                for item in bill_items:
                    p_no = item["part"]
                    q_sold = item["qty"]
                    current_stock = int(df.loc[df['part_number'] == p_no, 'stock_qty'].values[0])
                    if current_stock >= q_sold:
                        df.loc[df['part_number'] == p_no, 'stock_qty'] -= q_sold
                        df.loc[df['part_number'] == p_no, 'units_sold'] += q_sold
                    else:
                        st.error(f"Error: Not enough stock for {p_no}!")
                        sale_success = False
                
                if sale_success:
                    save_data(df)
                    
                    now_stamp = pd.Timestamp.now()
                    time_str = now_stamp.strftime('%Y-%m-%d %H:%M:%S')
                    items_summary = "; ".join([f"{i['desc']} x{i['qty']}" for i in bill_items])
                    
                    new_sale_dict = {
                        'timestamp': time_str,
                        'customer_name': cust_name.strip(),
                        'items_detail': items_summary,
                        'parts_total': float(parts_mrp_total),
                        'service_charge': float(service_charge),
                        'discount': float(discount_val),
                        'grand_total': float(final_grand_total),
                        'total_cost': float(parts_cost_total),
                        'net_profit': float(expected_net_profit),
                        'month_year': now_stamp.strftime('%Y-%m')
                    }
                    
                    save_sale_to_cloud(new_sale_dict)
                    
                    pdf_path = generate_invoice_pdf(
                        cust_name.strip(), 
                        bill_items, 
                        parts_mrp_total, 
                        total_cgst, 
                        total_sgst, 
                        service_charge, 
                        discount_val, 
                        final_grand_total, 
                        time_str
                    )
                    
                    with open(pdf_path, "rb") as pdf_file:
                        st.session_state['last_pdf_bytes'] = pdf_file.read()
                        
                    st.session_state['last_pdf_filename'] = f"Invoice_{cust_name.strip().replace(' ', '_')}_{now_stamp.strftime('%Y%m%d_%H%M%S')}.pdf"
                    
                    cleaned_phone = re.sub(r'\D', '', cust_phone_10.strip())
                    if len(cleaned_phone) == 10:
                        full_whatsapp_number = f"{country_code.strip()}{cleaned_phone}"
                        wa_message = (
                            f"Hello *{cust_name.strip()}*, thank you for visiting *SEEMA TVS*! "
                            f"Your bill summary for total Rs. *{final_grand_total:.2f}* has been generated. "
                            f"Please find your official tax invoice attached."
                        )
                        encoded_wa_msg = urllib.parse.quote(wa_message)
                        st.session_state['last_whatsapp_url'] = f"https://wa.me/{full_whatsapp_number}?text={encoded_wa_msg}"
                    else:
                        st.session_state['last_whatsapp_url'] = ""

                    st.session_state['sale_completed'] = True

                    try:
                        os.remove(pdf_path)
                    except Exception:
                        pass
                    st.rerun()

        if st.session_state.get('sale_completed', False):
            st.success("Sale completed successfully! Inventory & sales report updated.")
            
            if 'last_pdf_bytes' in st.session_state:
                st.download_button(
                    label="📄 Download Generated Tax Invoice (PDF)",
                    data=st.session_state['last_pdf_bytes'],
                    file_name=st.session_state.get('last_pdf_filename', 'Invoice.pdf'),
                    mime="application/pdf"
                )
            
            if st.session_state.get('last_whatsapp_url'):
                st.markdown(
                    f"""
                    <a href="{st.session_state['last_whatsapp_url']}" target="_blank">
                        <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; font-size:16px; border-radius:5px; cursor:pointer; font-weight:bold; width:100%; margin-top:10px;">
                            💬 Send Bill Summary on WhatsApp
                        </button>
                    </a>
                    """,
                    unsafe_allow_html=True
                )
                st.caption("Tip: Download the PDF above first, tap the WhatsApp button to open chat with the customer, and attach your downloaded file.")
            else:
                st.info("💡 Enter a valid 10-digit customer WhatsApp number before checkout to activate the direct WhatsApp share button.")

    with tab4:
        st.subheader("Sales Performance & Monthly Profit Reports")
        
        if not sales_df.empty:
            num_cols_s = ['parts_total', 'service_charge', 'discount', 'grand_total', 'total_cost', 'net_profit']
            for col in num_cols_s:
                sales_df[col] = pd.to_numeric(sales_df[col], errors='coerce').fillna(0)

            unique_months = sorted(sales_df['month_year'].dropna().astype(str).unique().tolist(), reverse=True)
            months = ["All Months"] + unique_months
            selected_month = st.selectbox("Select Reporting Month", months)
            
            if selected_month != "All Months":
                filtered_sales = sales_df[sales_df['month_year'] == selected_month]
            else:
                filtered_sales = sales_df.copy()
                
            st.markdown("---")
            
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric("Total Transactions", len(filtered_sales))
            with m_col2:
                st.metric("Total Revenue (Sales)", f"Rs. {filtered_sales['grand_total'].sum():,.2f}")
            with m_col3:
                st.metric("Total Costs", f"Rs. {filtered_sales['total_cost'].sum():,.2f}")
            with m_col4:
                st.metric("Net Profit", f"Rs. {filtered_sales['net_profit'].sum():,.2f}")

            st.markdown("---")
            st.markdown("### Transaction Log & Details")
            
            st.dataframe(filtered_sales, use_container_width=True)

            csv_data = filtered_sales.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Selected Sales Data (CSV)",
                data=csv_data,
                file_name=f"Sales_Report_{selected_month}.csv",
                mime="text/csv"
            )
        else:
            st.info("No sales transactions found yet.")
            
