import streamlit as st
import pandas as pd
import re
import requests
import io
import time
import os
from PIL import Image
import pytesseract
import shutil

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
                payload = {
                    "type": "inventory",
                    "data": df_to_save[EXPECTED_COLS].to_dict(orient="records")
                }
                response = requests.post(WEB_APP_URL, json=payload, timeout=15)
                
            if response.status_code == 200:
                st.sidebar.success("Successfully synced!")
            else:
                st.sidebar.error(f"Sync failed: {response.status_code}")
    except Exception as e:
        st.sidebar.error(f"Float/Sync error: {e}")

def load_sales_log():
    try:
        if WEB_APP_URL:
            response = requests.get(f"{WEB_APP_URL}?action=get_sales", timeout=15)
            if response.status_code == 200:
                sales_data = response.json()
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

df = load_data()
sales_df = load_sales_log()

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
        
        # 1. Extract Part Number
        if not part_no:
            match_pn = re.search(r'\b[A-Z]{2}\d{6}\b', line_upper)
            if match_pn:
                part_no = match_pn.group(0)
        
        # 2. Extract MRP
        if mrp_val == 0.0 and ("MRP" in line_upper or "RS" in line_upper):
            match_mrp = re.findall(r'(\d+\.\d{2})', line)
            if match_mrp:
                mrp_val = float(match_mrp[-1])
                
        # 3. Extract Description
        if not description:
            if any(keyword in line_upper for keyword in ["COMP", "FILTER", "KIT", "ASSY", "CABLE", "PAD", "SHOE", "VALVE", "GEAR"]):
                description = line.strip()

    if not description and len(cleaned_lines) > 2:
        for line in cleaned_lines:
            if len(line) > 5 and not any(w in line.upper() for w in ["MRP", "NET", "QUANTITY", "MANUFACTURED", "TVS", "TAXES"]):
                if not re.search(r'\b[A-Z]{2}\d{6}\b', line.upper()):
                    description = line.strip()
                    break

    if mrp_val == 0.0:
        for line in cleaned_lines:
            match_all_nums = re.findall(r'(\d+\.\d{2})', line)
            if match_all_nums:
                mrp_val = float(match_all_nums[0])
                break

    return part_no, description, mrp_val

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

# Check if scanned part already exists in database
existing_match = False
if scanned_part and not df.empty and 'part_number' in df.columns:
    existing_match = scanned_part in df['part_number'].values

if existing_match:
    st.sidebar.info(f"ℹ️ Part **{scanned_part}** is already in your database!")
    st.sidebar.header("📦 Quick Stock In (Duplicate Guard)")
    
    add_qty_val = st.sidebar.number_input("Add Quantity to Stock", min_value=1, value=1, step=1, key="quick_add_qty")
    if st.sidebar.button("Confirm Restock"):
        current_stock = int(df.loc[df['part_number'] == scanned_part, 'stock_qty'].values[0])
        df.loc[df['part_number'] == scanned_part, 'stock_qty'] = current_stock + add_qty_val
        save_data(df)
        st.sidebar.success(f"Added {add_qty_val} units to {scanned_part}!")
        time.sleep(1)
        st.rerun()
else:
    # 1. ADD NEW PART
    st.sidebar.header("➕ Add New Part")
    with st.sidebar.form("add_part_form", clear_on_submit=True):
        new_part_no = st.text_input("Part Number", value=scanned_part)
        new_desc = st.text_input("Description", value=scanned_desc)
        new_model = st.text_input("Model", value="Universal")
        
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

# 2. MANUAL STOCK ADJUSTMENT
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
        edited_df = st.data_editor(df.drop(columns=['status'], errors='ignore'), num_rows="dynamic", key="editor")
        if st.button("Save Changes to Google Sheet"):
            save_data(edited_df)
            time.sleep(1)
            st.rerun()

    with tab3:
        st.subheader("Record New Sale Transaction")
        st.caption("Select sold items, apply service charges or discounts, and complete checkout to update inventory and sales reports.")
        
        cust_name = st.text_input("Customer / Reference Name", value="Walk-in Customer")
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
                    st.write(f"**{part}** - {desc} (MRP: ₹{mrp} | Cost: ₹{cost}) | Stock: {avail_qty}")
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
                service_charge = st.number_input("Service / Labor Charge (₹)", min_value=0.0, value=0.0, step=10.0)
            with col_add2:
                discount_val = st.number_input("Discount (₹)", min_value=0.0, value=0.0, step=10.0)
                
            final_grand_total = max(0.0, parts_mrp_total + service_charge - discount_val)
            expected_net_profit = final_grand_total - parts_cost_total
            
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                st.metric("Parts Total (MRP)", f"₹{parts_mrp_total:.2f}")
            with col_p2:
                st.metric("Grand Total (Sale Price)", f"₹{final_grand_total:.2f}")
            with col_p3:
                st.metric("Net Profit", f"₹{expected_net_profit:.2f}")
            
            if st.button("Complete Checkout & Record Sale", type="primary"):
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
                    
                    # Record transaction to cloud sales log
                    now_stamp = pd.Timestamp.now()
                    items_summary = "; ".join([f"{i['part']} ({i['desc']}) x{i['qty']}" for i in bill_items])
                    
                    new_sale_dict = {
                        'timestamp': now_stamp.strftime('%Y-%m-%d %H:%M:%S'),
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
                    
                    st.success("Sale completed! Inventory updated and transaction saved to reports.")
                    time.sleep(1)
                    st.rerun()

    with tab4:
        st.subheader("Sales Performance & Monthly Profit Reports")
        
        if not sales_df.empty:
            num_cols_s = ['parts_total', 'service_charge', 'discount', 'grand_total', 'total_cost', 'net_profit']
            for col in num_cols_s:
                sales_df[col] = pd.to_numeric(sales_df[col], errors='coerce').fillna(0)

            # Month Selector Filter
            months = ["All Months"] + sorted(sales_df['month_year'].astype(str).unique().tolist(), reverse=True)
            selected_month = st.selectbox("Select Reporting Month", months)
            
            if selected_month != "All Months":
                filtered_sales = sales_df[sales_df['month_year'] == selected_month]
            else:
                filtered_sales = sales_df.copy()
                
            st.markdown("---")
            
            # High-level Metrics
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric("Total Transactions", len(filtered_sales))
            with m_col2:
                st.metric("Total Revenue (Sales)", f"₹{filtered_sales['grand_total'].sum():,.2f}")
            with m_col3:
                st.metric("Total Costs", f"₹{filtered_sales['total_cost'].sum():,.2f}")
            with m_col4:
                st.metric("Net Profit", f"₹{filtered_sales['net_profit'].sum():,.2f}")

            st.markdown("---")
            st.markdown("### Transaction Log & Details")
            
            # Export sales records
            csv_data = filtered_sales.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Selected Sales Data (CSV)",
                data=csv_data,
                file_name=f"Sales_Report_{selected_month}.csv",
                mime="text/csv"
            )
            
            st.dataframe(
                filtered_sales[['timestamp', 'customer_name', 'items_detail', 'grand_total', 'total_cost', 'net_profit', 'month_year']],
                use_container_width=True
            )
            
            with st.expander("🔍 View Detailed Line-by-Line Transactions"):
                for idx, row in filtered_sales.iloc[::-1].iterrows():
                    st.markdown(f"**Date:** {row['timestamp']} | **Customer:** {row['customer_name']} | **Month:** {row['month_year']}")
                    st.write(f"**Items:** {row['items_detail']}")
                    st.write(f"Parts Subtotal: ₹{row['parts_total']:.2f} | Service: +₹{row['service_charge']:.2f} | Discount: -₹{row['discount']:.2f}")
                    st.write(f"**Grand Total:** ₹{row['grand_total']:.2f} | **Unit Costs:** ₹{row['total_cost']:.2f} | **Profit:** ₹{row['net_profit']:.2f}")
                    st.divider()
        else:
            st.info("No sales recorded yet. Use the 'Record Sale' tab to log your first transaction!")
else:
    st.info("Your inventory database is currently empty.")
