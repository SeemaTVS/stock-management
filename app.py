with tab5:
        st.subheader("📂 Upload Trimmed Excel Master File")
        st.caption("Upload your trimmed Excel file. Zero/blank quantity items are filtered out, stock initializes to 0, and multi-bike/ALL names map to Universal.")
        
        uploaded_excel = st.file_uploader("Choose Excel File (.xlsx)", type=["xlsx"])
        if uploaded_excel:
            try:
                # Read without assuming header row immediately to inspect all rows safely
                raw_excel = pd.read_excel(uploaded_excel, header=None)
                
                # Find the header row dynamically by looking for cells containing 'PART' or 'MRP'
                header_row_idx = 0
                for idx, row in raw_excel.iterrows():
                    row_str = " ".join([str(val).upper() for val in row.values])
                    if 'PART' in row_str or 'MRP' in row_str or 'PARTS' in row_str:
                        header_row_idx = idx
                        break
                
                # Reload properly using the detected header row
                excel_df = pd.read_excel(uploaded_excel, header=header_row_idx)
                
                # Clean column names
                excel_df.columns = [str(c).strip().upper() for c in excel_df.columns]
                st.write(f"Detected columns: {list(excel_df.columns)}")
                
                if st.button("Process & Import Master Inventory", type="primary"):
                    # Map columns dynamically based on keywords
                    col_name = next((c for c in excel_df.columns if 'NAME' in c or 'PART NAME' in c), excel_df.columns[0])
                    col_part = next((c for c in excel_df.columns if 'NO' in c or 'PARTS NO' in c), excel_df.columns[1])
                    col_bike = next((c for c in excel_df.columns if 'BIKE' in c or 'MODEL' in c), excel_df.columns[2])
                    col_mrp = next((c for c in excel_df.columns if 'MRP' in c), excel_df.columns[3])
                    col_qty = next((c for c in excel_df.columns if 'QTY' in c or 'QUANTITY' in c), excel_df.columns[4])
                    
                    # Drop rows where part number is missing
                    excel_df = excel_df.dropna(subset=[col_part])
                    
                    # Filter out 0 or blank quantities
                    excel_df[col_qty] = pd.to_numeric(excel_df[col_qty], errors='coerce').fillna(0)
                    excel_df = excel_df[excel_df[col_qty] > 0]
                    
                    imported_count = 0
                    for _, row in excel_df.iterrows():
                        p_num = str(row[col_part]).strip()
                        if not p_num or p_num.lower() == 'nan' or p_num == 'PARTS NO.':
                            continue
                            
                        desc = str(row[col_name]).strip()
                        if desc.lower() == 'nan' or desc == 'PART NAME':
                            desc = ""
                            
                        mrp_val = float(row[col_mrp]) if pd.notnull(row[col_mrp]) and str(row[col_mrp]).replace('.','',1).isdigit() else 0.0
                        cost_val = round(mrp_val * 0.84, 2)
                        
                        raw_bike = str(row[col_bike]).strip()
                        if ',' in raw_bike or 'all' in raw_bike.lower():
                            model_val = "Universal"
                        else:
                            model_val = raw_bike if raw_bike and raw_bike.lower() != 'nan' else "Universal"
                            
                        # Check if part exists and update or add
                        if not df.empty and p_num in df['part_number'].values:
                            df.loc[df['part_number'] == p_num, 'description'] = desc
                            df.loc[df['part_number'] == p_num, 'model'] = model_val
                            df.loc[df['part_number'] == p_num, 'unit_mrp'] = mrp_val
                            df.loc[df['part_number'] == p_num, 'unit_cost'] = cost_val
                        else:
                            new_row = pd.DataFrame([{
                                'part_number': p_num,
                                'description': desc,
                                'model': model_val,
                                'unit_cost': cost_val,
                                'unit_mrp': mrp_val,
                                'stock_qty': 0,
                                'min_threshold': 5,
                                'units_sold': 0
                            }])
                            df = pd.concat([df, new_row], ignore_index=True)
                        imported_count += 1
                        
                    save_data(df)
                    st.success(f"Successfully processed and imported {imported_count} items from Excel!")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"Error processing Excel file: {e}")
