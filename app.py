import streamlit as st
import pandas as pd
import re
import requests
import io
import time
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import shutil
import urllib.parse

# Automatically find Tesseract whether running locally or on Streamlit Cloud
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
        st.error(f"Load error: {e}")
        return pd.DataFrame(columns=EXPECTED_COLS)

def save_data(df_to_save):
    try:
        for col in EXPECTED_COLS:
            if col not in df_to_save.columns:
                df_to_save[col] = ""
        
        num_cols = ['unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold']
        for col in num_cols:
            df_to_save[col] = pd.to_numeric(df_to_save[col], errors='coerce').fillna(0)
            
        df_to_save['part_number'] = df_to_save['part_number'].astype(str).str.strip()
        df_to_save = df_to_save.dropna(subset=['part_number'])
        df_to_save = df_to_save[df_to_save['part_number'] != ""]

        if WEB_APP_URL:
            with st.spinner("Syncing changes to Google Sheet..."):
                data_dict = df_to_save[EXPECTED_COLS].to_dict(orient="records")
                response = requests.post(WEB_APP_URL, json=data_dict, timeout=15)
                
            if response.status_code == 200:
                st.sidebar.success("Successfully synced!")
            else:
                st.sidebar.error(f"Sync failed: {response.status_code}")
    except Exception as e:
        st.sidebar.error(f"Float/Sync error: {e}")

df = load_data()

# Smart OCR Parser: Extracts Part Number, Description, and MRP from TVS Label
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
        
        # 1. Extract Part Number (e.g. NF040370)
        if not part_no:
            match_pn = re.search(r'\b[A-Z]{2}\d{6}\b', line_upper)
            if match_pn:
                part_no = match_pn.group(0)
        
        # 2. Extract MRP (e.g. MRP Rs. 298.00 or 298.00)
        if mrp_val == 0.0 and ("MRP" in line_upper or "RS" in line_upper):
            match_mrp = re.findall(r'(\d+\.\d{2})', line)
            if match_mrp:
                mrp_val = float(match_mrp[-1]) # Usually last decimal in MRP line
                
        # 3. Extract Description (Usually contains words like COMP, FILTER, KIT, etc. or appears in capital letters mid-label)
        if not description:
            if any(keyword in line_upper for keyword in ["COMP", "FILTER", "KIT", "ASSY", "CABLE", "PAD", "SHOE", "VALVE", "GEAR"]):
                description = line.strip()

    # Fallback search if description wasn't caught by keywords
    if not description and len(cleaned_lines) > 2:
        for line in cleaned_lines:
            if len(line) > 5 and not any(w in line.upper() for w in ["MRP", "NET", "QUANTITY", "MANUFACTURED", "TVS", "TAXES"]):
                if not re.search(r'\b[A-Z]{2}\d{6}\b', line.upper()):
                    description = line.strip()
                    break

    # Fallback MRP check if missed
    if mrp_val == 0.0:
        for line in cleaned_lines:
            match_all_nums = re.findall(r'(\d+\.\d{2})', line)
            if match_all_nums:
                mrp_val = float(match_all_nums[0])
                break

    return part_no, description, mrp_val

# Branded Invoice Image Generator
def generate_receipt_image(cust_name, bill_items, service_charge, discount, final_total):
    img_width, img_height = 600, 950
    base_img = Image.new("RGB", (img_width, img_height), color="white")
    
    txt_layer = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
    try:
        font_wm = ImageFont.truetype("arial.ttf", 60)
        font_logo = ImageFont.truetype("arial.ttf", 40)
    except IOError:
        font_wm = ImageFont.load_default()
        font_logo = ImageFont.load_default()

    draw_wm = ImageDraw.Draw(txt_layer)
    draw_wm.text((120, 320), "SEEMA TVS", fill=(180, 200, 230, 130), font=font_logo)
    
    rotated_txt = txt_layer.rotate(25, expand=1)
    base_img.paste(rotated_txt, (-50, -50), rotated_txt)

    draw = ImageDraw.Draw(base_img)
    
    try:
        font_title = ImageFont.truetype("arial.ttf", 26)
        font_header = ImageFont.truetype("arial.ttf", 16)
        font_bold = ImageFont.truetype("arial.ttf", 14)
        font_regular = ImageFont.truetype("arial.ttf", 14)
    except IOError:
        font_title = ImageFont.load_default()
        font_header = ImageFont.load_default()
        font_bold = ImageFont.load_default()
        font_regular = ImageFont.load_default()

    draw.text((180, 30), "SEEMA TVS AGENCY", fill="black", font=font_title)
    draw.text((210, 65), "Official Spare Parts Bill", fill="gray", font=font_header)
    draw.line([(30, 100), (570, 100)], fill="black", width=2)
    
    draw.text((30, 120), f"Customer Name: {cust_name}", fill="black", font=font_bold)
    draw.text((30, 145), f"Date: {pd.Timestamp.now().strftime('%d-%m-%Y %H:%M')}", fill="black", font=font_regular)
    draw.line([(30, 175), (570, 175)], fill="gray", width=1)
    
    draw.text((30, 190), "Part # / Description", fill="black", font=font_bold)
    draw.text((380, 190), "Qty", fill="black", font=font_bold)
    draw.text((460, 190), "Amount", fill="black", font=font_bold)
    draw.line([(30, 215), (570, 215)], fill="black", width=1)
    
    y_offset = 230
    for item in bill_items:
        draw.text((30, y_offset), f"{item['part']}", fill="black", font=font_bold)
        draw.text((30, y_offset + 20), f"{item['desc']}", fill="gray", font=font_regular)
        draw.text((380, y_offset + 10), f"{item['qty']}", fill="black", font=font_regular)
        draw.text((460, y_offset + 10), f"Rs. {item['total']:.2f}", fill="black", font=font_regular)
        y_offset += 60
        
    draw.line([(30, y_offset + 10), (570, y_offset + 10)], fill="black", width=1)
    
    y_offset += 20
    draw.text((30, y_offset), "Subtotal Parts:", fill="black", font=font_regular)
    subtotal_parts = sum(i['total'] for i in bill_items)
    draw.text((460, y_offset), f"Rs. {subtotal_parts:.2f}", fill="black", font=font_regular)
    
    if service_charge > 0:
        y_offset += 30
        draw.text((30, y_offset), "Service Charge:", fill="black", font=font_regular)
        draw.text((460, y_offset), f"+ Rs. {service_charge:.2f}", fill="black", font=font_regular)
        
    if discount > 0:
        y_offset += 30
        draw.text((30, y_offset), "Discount Applied:", fill="black", font=font_regular)
        draw.text((460, y_offset), f"- Rs. {discount:.2f}", fill="black", font=font_regular)
        
    draw.line([(30, y_offset + 30), (570, y_offset + 30)], fill="black", width=2)
    
    draw.text((30, y_offset + 50), "GRAND TOTAL:", fill="black", font=font_title)
    draw.text((400, y_offset + 50), f"Rs. {final_total:.2f}", fill="black", font=font_title)
    
    draw.line([(30, y_offset + 110), (570, y_offset + 110)], fill="gray", width=1)
    draw.text((200, y_offset + 130), "Thank you for your business! 🙏", fill="black", font=font_bold)
    
    final_img = base_img.crop((0, 0, img_width, y_offset + 180))
    
    buf = io.BytesIO()
    final_img.save(buf, format="PNG")
    buf.seek(0)
    return buf

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
            st.sidebar.success(f"Detected: {scanned_part}")
        else:
            st.sidebar.warning("Could not auto-detect part number.")
    except Exception as e:
        st.sidebar.error(f"Scanner Error: {e}")

st.sidebar.markdown("---")

# 1. ADD NEW PART (Auto-filled with Scanner data & 16% unit cost formula)
st.sidebar.header("➕ Add New Part")
with st.sidebar.form("add_part_form", clear_on_submit=True):
    new_part_no = st.text_input("Part Number", value=scanned_part)
    new_desc = st.text_input("Description", value=scanned_desc)
    new_model = st.text_input("Model", value="Universal")
    
    # Auto formula: Unit Cost = MRP - 16%
    default_mrp = float(scanned_mrp) if scanned_mrp > 0 else 0.0
    new_mrp = st.number_input("Unit MRP (₹)", min_value=0.0, value=default_mrp, step=1.0)
    default_cost = round(new_mrp * 0.84, 2) if new_mrp > 0 else 0.0
    
    new_cost = st.number_input("Unit Cost (₹ [MRP - 16%])", min_value=0.0, value=default_cost, step=1.0)
    new_qty = st.number_input("Initial Stock", min_value=0, value=1, step=1)
    new_min = st.number_input("Min Threshold", min_value=1, value=5, step=1)
    
    submit_new_part = st.form_submit_button("Add to Database")
    
    if submit_new_part:
        if not new_part_no.strip():
            st.sidebar.error("Part Number is required!")
        else:
            new_row = pd.DataFrame([{
                'part_number': new_part_no.strip(),
                'description': new_desc.strip(),
                'model': new_model.strip(),
                'unit_cost': float(new_cost),
                'unit_mrp': float(new_mrp),
                'stock_qty': int(new_qty),
                'min_threshold': int(new_min),
                'units_sold': 0
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            time.sleep(1)
            st.rerun()

st.sidebar.markdown("---")

# 2. MANUAL STOCK ADJUSTMENT (At the bottom)
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
                time.sleep(1)
                st.rerun()
        with col2:
            if st.sidebar.button("Record Sale"):
                current_stock = int(df.loc[df['part_number'] == selected_part, 'stock_qty'].values[0])
                if current_stock >= qty_change:
                    df.loc[df['part_number'] == selected_part, 'stock_qty'] -= qty_change
                    df.loc[df['part_number'] == selected_part, 'units_sold'] += qty_change
                    save_data(df)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error("Insufficient stock!")

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

    tab1, tab2, tab3 = st.tabs([
        "📊 Overview & Stock", 
        "✏️ Edit Master Data", 
        "📱 Seema TVS Billing"
    ])

    with tab1:
        st.subheader("Current Stock Inventory")
        st.dataframe(df[['part_number', 'description', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'units_sold', 'status']], use_container_width=True)

    with tab2:
        st.subheader("Interactive Master Data Editor")
        edited_df = st.data_editor(df.drop(columns=['status'], errors='ignore'), num_rows="dynamic", key="editor")
        if st.button("Save Changes to Google Sheet"):
            save_data(edited_df)
            time.sleep(1)
            st.rerun()

    with tab3:
        st.subheader("Seema TVS Branded Invoice Generator")
        st.caption("Select items, apply service charges or discounts, generate the branded receipt image, and send it over WhatsApp.")
        
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            cust_name = st.text_input("Customer Name", value="Customer")
        with col_b2:
            cust_phone = st.text_input("Customer WhatsApp Number (with country code, e.g., 919876543210)", value="")

        selected_billing_parts = st.multiselect("Select Parts Sold", df['part_number'].tolist(), key="img_bill_parts")
        
        bill_items = []
        parts_total = 0.0
        
        if selected_billing_parts:
            st.markdown("### Item Quantities")
            for part in selected_billing_parts:
                row_data = df[df['part_number'] == part].iloc[0]
                desc = row_data['description']
                mrp = float(row_data['unit_mrp'])
                avail_qty = int(row_data['stock_qty'])
                
                col_q1, col_q2 = st.columns([3, 1])
                with col_q1:
                    st.write(f"**{part}** - {desc} (MRP: ₹{mrp}) | Stock: {avail_qty}")
                with col_q2:
                    qty_sold = st.number_input(f"Qty [{part}]", min_value=1, max_value=max(1, avail_qty), value=1, key=f"img_qty_{part}")
                
                item_total = mrp * qty_sold
                parts_total += item_total
                bill_items.append({"part": part, "desc": desc, "qty": qty_sold, "mrp": mrp, "total": item_total})
            
            st.markdown("---")
            col_add1, col_add2 = st.columns(2)
            with col_add1:
                service_charge = st.number_input("Service / Labor Charge (₹)", min_value=0.0, value=0.0, step=10.0)
            with col_add2:
                discount_val = st.number_input("Discount (₹)", min_value=0.0, value=0.0, step=10.0)
                
            final_grand_total = max(0.0, parts_total + service_charge - discount_val)
            st.markdown(f"### **Final Grand Total: ₹{final_grand_total:.2f}**")
            
            if st.button("Deduct Stock & Generate Invoice"):
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
                    st.success("Sale completed and inventory updated in Google Sheet!")
                    
                    receipt_buf = generate_receipt_image(cust_name, bill_items, service_charge, discount_val, final_grand_total)
                    
                    st.markdown("### 📥 Download Branded Receipt Image")
                    st.image(receipt_buf, caption="Generated Seema TVS Branded Invoice", width=400)
                    
                    st.download_button(
                        label="Download Invoice Image (PNG)",
                        data=receipt_buf,
                        file_name=f"Seema_TVS_Invoice_{cust_name}.png",
                        mime="image/png"
                    )
                    
                    wa_text = f"*--- 📋 SEEMA TVS INVOICE ---*\n*Customer:* {cust_name}\n*Total:* ₹{final_grand_total:.2f}\n🙏 Thank you for choosing Seema TVS!"
                    encoded_wa = urllib.parse.quote(wa_text)
                    wa_link = f"https://wa.me/{cust_phone}?text={encoded_wa}" if cust_phone else f"https://wa.me/?text={encoded_wa}"
                    
                    st.markdown(f"👉 **[Click to Open WhatsApp]({wa_link})**", unsafe_allow_html=True)
else:
    st.info("Your inventory database is currently empty.")
