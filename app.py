import streamlit as st
import pandas as pd
import re
import os
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import shutil
import requests
import io
import urllib.parse

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

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Y4yyok1dtw0RZyhc46vwHZ4frW9SyTsHCXMBSpegWlM/edit?gid=0#gid=0"
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbymkbPavkWPw_5kFEN7S6KQTg2MvS_zqAmGXXkqBAjVDo7XrnUCj9GKKKrA_heBvWZvmQ/exec"

def get_csv_export_url(sheet_url):
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
    if match:
        sheet_id = match.group(1)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    return sheet_url

CSV_EXPORT_URL = get_csv_export_url(GOOGLE_SHEET_URL)
EXPECTED_COLS = ['part_number', 'description', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'units_sold']

# 1. Load Data from Google Sheet
def load_data():
    try:
        df_loaded = pd.read_csv(CSV_EXPORT_URL)
        for col_to_drop in ['category', 'max_capacity']:
            if col_to_drop in df_loaded.columns:
                df_loaded = df_loaded.drop(columns=[col_to_drop])
        
        for col in EXPECTED_COLS:
            if col not in df_loaded.columns:
                df_loaded[col] = ""
                
        if 'units_sold' not in df_loaded.columns:
            df_loaded['units_sold'] = 0
            
        df_loaded = df_loaded.dropna(subset=['part_number'])
        return df_loaded
    except Exception:
        return pd.DataFrame(columns=EXPECTED_COLS)

def save_data(df_to_save):
    for col_to_drop in ['category', 'max_capacity', 'status']:
        if col_to_drop in df_to_save.columns:
            df_to_save = df_to_save.drop(columns=[col_to_drop])
            
    for col in EXPECTED_COLS:
        if col not in df_to_save.columns:
            df_to_save[col] = 0
            
    if WEB_APP_URL:
        try:
            data_dict = df_to_save[EXPECTED_COLS].to_dict(orient="records")
            response = requests.post(WEB_APP_URL, json=data_dict)
            if response.status_code == 200:
                st.sidebar.success("Successfully synced to Google Sheet!")
            else:
                st.sidebar.error("Failed to sync with Google Sheet.")
        except Exception as e:
            st.sidebar.error(f"Sync error: {e}")

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

# Helper function to generate receipt image with diagonally tilted colored watermark & TVS logo
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
    draw_wm.text((120, 320), "TVS [LOGO]", fill=(180, 200, 230, 130), font=font_logo)
    draw_wm.text((60, 410), "SEEMA TVS", fill=(170, 195, 230, 140), font=font_wm)
    
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

    # Header Details
    draw.text((180, 30), "SEEMA TVS AGENCY", fill="black", font=font_title)
    draw.text((210, 65), "Official Spare Parts Bill", fill="gray", font=font_header)
    draw.line([(30, 100), (570, 100)], fill="black", width=2)
    
    # Customer Info
    draw.text((30, 120), f"Customer Name: {cust_name}", fill="black", font=font_bold)
    draw.text((30, 145), f"Date: {pd.Timestamp.now().strftime('%d-%m-%Y %H:%M')}", fill="black", font=font_regular)
    draw.line([(30, 175), (570, 175)], fill="gray", width=1)
    
    # Table Headers
    draw.text((30, 190), "Part # / Description", fill="black", font=font_bold)
    draw.text((380, 190), "Qty", fill="black", font=font_bold)
    draw.text((460, 190), "Amount", fill="black", font=font_bold)
    draw.line([(30, 215), (570, 215)], fill="black", width=1)
    
    # Item Rows
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
    
    if not df.empty and 'part_number' in df.columns and active_part in df['part_number'].values:
        if st.sidebar.button("Add +1 to Stock"):
            df.loc[df['part_number'] == active_part, 'stock_qty'] += 1
            save_data(df)
            st.rerun()
    else:
        st.sidebar.warning(f"Part '{active_part}' not found in database.")
        default_new_part = active_part

st.sidebar.markdown("---")

st.sidebar.header("⚙️ Manual Stock Adjustment")
part_options = df['part_number'].unique() if not df.empty and 'part_number' in df.columns else []
selected_part = st.sidebar.selectbox("Select Part to Update", part_options)

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
        elif not df.empty and 'part_number' in df.columns and new_part_no in df['part_number'].values:
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
if not df.empty and 'part_number' in df.columns and len(df) > 0:
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
        "🚨 Reorder Alerts", 
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
            st.rerun()

    with tab3:
        st.subheader("Stock Requiring Attention")
        low_stock = df[df['status'].isin(["OUT OF STOCK", "REORDER NEEDED"])]
        if not low_stock.empty:
            st.warning(f"Found {len(low_stock)} items that need restocking!")
            st.dataframe(low_stock[['part_number', 'description', 'stock_qty', 'min_threshold', 'status']], use_container_width=True)
        else:
            st.success("All inventory levels are healthy!")

    with tab4:
        st.subheader("Seema TVS Branded Invoice Generator")
        st.caption("Select items, add service charges/discounts, and generate a branded receipt image for WhatsApp downloads.")
        
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
                    current_stock = df.loc[df['part_number'] == p_no, 'stock_qty'].values[0]
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
                    
                    st.markdown("### 📥 Download Branded Receipt Image & Structured Text")
                    st.image(receipt_buf, caption="Generated Seema TVS Branded Invoice", width=400)
                    
                    st.download_button(
                        label="Download Invoice Image (PNG)",
                        data=receipt_buf,
                        file_name=f"Seema_TVS_Invoice_{cust_name}.png",
                        mime="image/png"
                    )
                    
                    wa_invoice = f"*--- 📋 SEEMA TVS INVOICE ---*\n"
                    wa_invoice += f"*Customer:* {cust_name}\n"
                    wa_invoice += f"*Date:* {pd.Timestamp.now().strftime('%d-%m-%Y %H:%M')}\n"
                    wa_invoice += f"--------------------------------\n"
                    for itm in bill_items:
                        wa_invoice += f"• *{itm['part']}* ({itm['desc']})\n"
                        wa_invoice += f"  Qty: {itm['qty']} × ₹{itm['mrp']:.2f} = *₹{itm['total']:.2f}*\n"
                    wa_invoice += f"--------------------------------\n"
                    wa_invoice += f"Parts Subtotal: ₹{parts_total:.2f}\n"
                    if service_charge > 0:
                        wa_invoice += f"Service Charge: +₹{service_charge:.2f}\n"
                    if discount_val > 0:
                        wa_invoice += f"Discount: -₹{discount_val:.2f}\n"
                    wa_invoice += f"--------------------------------\n"
                    wa_invoice += f"*GRAND TOTAL: ₹{final_grand_total:.2f}*\n"
                    wa_invoice += f"--------------------------------\n"
                    wa_invoice += f"🙏 Thank you for choosing Seema TVS!"
                    
                    encoded_wa = urllib.parse.quote(wa_invoice)
                    wa_link = f"https://wa.me/{cust_phone}?text={encoded_wa}" if cust_phone else f"https://wa.me/?text={encoded_wa}"
                    
                    st.markdown(f"👉 **[Click to Open WhatsApp with Structured Bill]({wa_link})**", unsafe_allow_html=True)
                    st.text_area("Or copy structured bill text manually:", value=wa_invoice, height=200)
else:
    st.info("Your inventory database is currently empty. Use the sidebar on the left to add your first part!")
