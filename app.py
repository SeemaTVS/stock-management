import streamlit as st
import pandas as pd
import json
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

try:
    from pyzbar.pyzbar import decode
    PYZBAR_AVAILABLE = True
except Exception:
    PYZBAR_AVAILABLE = False

st.title("TVS Agency Inventory & Order Management")

CSV_FILE = "inventory.csv"

def load_data():
    try:
        df = pd.read_csv(CSV_FILE)
        if 'category' in df.columns:
            df = df.drop(columns=['category'])
        return df
    except Exception:
        return pd.DataFrame(columns=[
            'part_number', 'description', 'model', 
            'unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 
            'max_capacity', 'units_sold'
        ])

def save_data(df_to_save):
    if 'category' in df_to_save.columns:
        df_to_save = df_to_save.drop(columns=['category'])
    base_cols = ['part_number', 'description', 'model', 'unit_cost', 'unit_mrp', 'stock_qty', 'min_threshold', 'max_capacity', 'units_sold']
    for col in base_cols:
        if col not in df_to_save.columns:
            df_to_save[col] = 0
    df_to_save.to_csv(CSV_FILE, index=False)

df = load_data()

if 'cart' not in st.session_state:
    st.session_state.cart = {}

st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Inventory Management", "Scanner", "Billing / POS", "Analytics & Reports"])

if page == "Dashboard":
    st.subheader("Inventory Dashboard")
    if not df.empty:
        total_items = len(df)
        total_stock = df['stock_qty'].sum() if 'stock_qty' in df.columns else 0
        low_stock_count = len(df[df['stock_qty'] <= df['min_threshold']]) if 'min_threshold' in df.columns else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Unique Parts", total_items)
        col2.metric("Total Stock Units", total_stock)
        col3.metric("Low Stock Alerts", low_stock_count, delta=-low_stock_count if low_stock_count > 0 else 0, delta_color="inverse")
        
        st.markdown("---")
        st.subheader("Current Stock Overview")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No inventory data loaded.")

elif page == "Inventory Management":
    st.subheader("Manage Inventory Items")
    if not df.empty:
        st.markdown("### Add / Remove or Edit Items")
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("Save Changes"):
            save_data(edited_df)
            st.success("Inventory updated successfully!")
    else:
        st.info("No data available to manage.")

elif page == "Scanner":
    st.subheader("Barcode / Image Scanner")
    uploaded_image = st.file_uploader("Upload barcode or part image", type=["png", "jpg", "jpeg"])
    if uploaded_image is not None:
        image = Image.open(uploaded_image)
        st.image(image, caption="Uploaded Image", use_container_width=True)
        
        extracted_text = pytesseract.image_to_string(image)
        st.write("**Extracted Text / Part Number:**")
        st.code(extracted_text)
        
        found_match = False
        for _, row in df.iterrows():
            if str(row['part_number']) in extracted_text:
                st.success(f"Found Match: {row['part_number']} - {row['description']}")
                st.write(f"Stock Qty: {row['stock_qty']} | MRP: ₹{row['unit_mrp']}")
                found_match = True
        if not found_match and extracted_text.strip():
            st.warning("No matching part number found in inventory.")

elif page == "Billing / POS":
    st.subheader("Point of Sale & Billing")
    if not df.empty:
        search_query = st.text_input("Search part number or description:")
        filtered_df = df[df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)] if search_query else df
        
        selected_part = st.selectbox("Select Part", filtered_df['part_number'].tolist() if not filtered_df.empty else [])
        
        if selected_part:
            part_row = df[df['part_number'] == selected_part].iloc[0]
            st.write(f"**Description:** {part_row.get('description', '')}")
            st.write(f"**Available Stock:** {part_row.get('stock_qty', 0)}")
            st.write(f"**MRP:** ₹{part_row.get('unit_mrp', 0)}")
            
            qty = st.number_input("Quantity", min_value=1, max_value=int(part_row.get('stock_qty', 1)), value=1)
            
            if st.button("Add to Cart"):
                st.session_state.cart[selected_part] = st.session_state.cart.get(selected_part, 0) + qty
                st.success(f"Added {qty} of {selected_part} to cart.")
        
        if st.session_state.cart:
            st.markdown("### Current Cart")
            cart_items = []
            total_amount = 0
            for part, q in st.session_state.cart.items():
                p_row = df[df['part_number'] == part].iloc[0]
                price = p_row.get('unit_mrp', 0)
                subtotal = price * q
                total_amount += subtotal
                cart_items.append({"Part Number": part, "Description": p_row.get('description', ''), "Qty": q, "Price": price, "Subtotal": subtotal})
            
            st.dataframe(pd.DataFrame(cart_items), use_container_width=True)
            st.write(f"**Total Bill Amount:** ₹{total_amount}")
            
            if st.button("Complete Checkout"):
                for part, q in st.session_state.cart.items():
                    idx = df[df['part_number'] == part].index[0]
                    df.loc[idx, 'stock_qty'] = max(0, df.loc[idx, 'stock_qty'] - q)
                    df.loc[idx, 'units_sold'] = df.loc[idx, 'units_sold'] + q
                save_data(df)
                st.session_state.cart = {}
                st.success("Checkout complete! Stock updated.")
                st.rerun()
    else:
        st.info("Please load inventory data first.")

elif page == "Analytics & Reports":
    st.subheader("Sales & Inventory Reports")
    if not df.empty and 'units_sold' in df.columns:
        st.bar_chart(df.set_index('part_number')['units_sold'])
    else:
        st.info("No sales data available.")
