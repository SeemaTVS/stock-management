# --- UPDATED ROBUST DEALER BILL PARSER ---
def parse_dealer_bill(img):
    parsed_items = []
    try:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        n_boxes = len(data.get('text', []))
        if n_boxes == 0:
            return []
        
        rows = {}
        for i in range(n_boxes):
            text = data['text'][i].strip()
            if not text:
                continue
            top = data['top'][i]
            
            row_key = None
            for existing_top in rows:
                if abs(existing_top - top) <= 14:
                    row_key = existing_top
                    break
            if row_key is None:
                row_key = top
                rows[row_key] = []
            rows[row_key].append((data['left'][i], text))
            
        sorted_row_keys = sorted(rows.keys())
        current_item = None
        
        for r_top in sorted_row_keys:
            line_words = sorted(rows[r_top], key=lambda x: x[0])
            line_tokens = [w[1] for w in line_words]
            if not line_tokens:
                continue
                
            line_text = " ".join(line_tokens)
            line_upper = line_text.upper()
            
            if any(w in line_upper for w in ['INVOICE', 'GSTIN', 'JURISDICTION', 'ADDRESS', 'MOBILE', 'S.N', 'PART NO', 'RATE', 'QTY', 'MRP', 'DISCOUNT', 'TAX', 'DELIVERY', 'RECIPIENT']):
                continue
                
            first_token = line_tokens[0].strip(".,")
            is_new_row = False
            if first_token.isdigit() and int(first_token) <= 50:
                if len(line_tokens) >= 2:
                    potential_pn = re.sub(r'[^A-Z0-9\-]', '', line_tokens[1].upper())
                    if len(potential_pn) >= 4:
                        is_new_row = True

            if is_new_row:
                if current_item:
                    parsed_items.append(current_item)
                
                part_no = re.sub(r'[^A-Z0-9\-]', '', line_tokens[1].upper())
                desc_words = []
                numeric_tokens_found = []
                
                for idx in range(2, len(line_tokens)):
                    tok = line_tokens[idx]
                    clean_tok = re.sub(r'[^0-9.]', '', tok)
                    if clean_tok and set(clean_tok) <= set('0123456789.'):
                        try:
                            val = float(clean_tok)
                            numeric_tokens_found.append(val)
                        except ValueError:
                            desc_words.append(tok)
                    else:
                        desc_words.append(tok)
                        
                qty = 1.0
                mrp = 0.0
                valid_prices = [n for n in numeric_tokens_found if n > 0]
                if len(valid_prices) >= 2:
                    potential_qtys = [n for n in valid_prices[:3] if n < 100 and n.is_integer()]
                    if potential_qtys:
                        qty = potential_qtys[0]
                        valid_prices.remove(qty)
                    mrp = valid_prices[-1]
                elif len(valid_prices) == 1:
                    mrp = valid_prices[0]

                current_item = {
                    "part_number": part_no,
                    "qty": int(qty),
                    "mrp": float(mrp),
                    "description_words": desc_words
                }
            else:
                if current_item is not None:
                    for tok in line_tokens:
                        clean_tok = re.sub(r'[^0-9.]', '', tok)
                        if clean_tok and set(clean_tok) <= set('0123456789.'):
                            try:
                                val = float(clean_tok)
                                if val > current_item["mrp"]:
                                    current_item["mrp"] = val
                            except ValueError:
                                current_item["description_words"].append(tok)
                        else:
                            current_item["description_words"].append(tok)
                            
        if current_item:
            parsed_items.append(current_item)
            
        finalized_items = []
        for item in parsed_items:
            clean_desc = " ".join(item["description_words"]).replace("/", " ").strip()
            clean_desc = re.sub(r'\s+', ' ', clean_desc)
            finalized_items.append({
                "part_number": item["part_number"],
                "qty": item["qty"],
                "mrp": item["mrp"],
                "description": clean_desc
            })
            
        return finalized_items
    except Exception:
        return []
