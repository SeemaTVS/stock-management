# --- REVISED ROBUST DEALER BILL PARSER ---
def parse_dealer_bill(img):
    parsed_items = []
    try:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        n_boxes = len(data['text'])
        
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
        
        for r_top in sorted_row_keys:
            line_words = sorted(rows[r_top], key=lambda x: x[0])
            line_tokens = [w[1] for w in line_words]
            line_text = " ".join(line_tokens)
            line_upper = line_text.upper()
            
            if any(w in line_upper for w in ['INVOICE', 'GSTIN', 'JURISDICTION', 'ADDRESS', 'MOBILE', 'S.N', 'PART NO', 'RATE', 'QTY', 'MRP', 'DISCOUNT', 'TAX', 'DELIVERY', 'RECIPIENT']):
                continue
                
            if not line_tokens:
                continue
                
            first_token = line_tokens[0].strip(".,")
            if not first_token.isdigit():
                continue
                
            serial_no = int(first_token)
            if serial_no > 50:
                continue
                
            part_no = ""
            part_token_idx = -1
            for idx in range(1, len(line_tokens)):
                candidate = line_tokens[idx].strip()
                clean_cand = re.sub(r'[^A-Z0-9\-]', '', candidate.upper())
                if len(clean_cand) >= 4 and not clean_cand.isdigit():
                    part_no = clean_cand
                    part_token_idx = idx
                    break
            
            if not part_no and len(line_tokens) > 1:
                candidate = line_tokens[1].strip()
                if len(candidate) >= 4:
                    part_no = re.sub(r'[^A-Z0-9\-]', '', candidate.upper())
                    part_token_idx = 1
                    
            if not part_no:
                continue
                
            desc_words = []
            numeric_tokens_found = []
            
            for idx in range(part_token_idx + 1, len(line_tokens)):
                tok = line_tokens[idx]
                clean_tok = re.sub(r'[^0-9.]', '', tok)
                
                if clean_tok and set(clean_tok) <= set('0123456789.'):
                    try:
                        numeric_tokens_found.append(float(clean_tok))
                    except ValueError:
                        desc_words.append(tok)
                else:
                    desc_words.append(tok)
                    
            clean_desc = " ".join(desc_words).replace("/", " ").strip()
            clean_desc = re.sub(r'\s+', ' ', clean_desc)
            if not clean_desc or len(clean_desc) < 2:
                clean_desc = f"TVS Part {part_no}"
                
            qty = 1.0
            mrp = 0.0
            
            valid_prices = [n for n in numeric_tokens_found if n > 0]
            
            if len(valid_prices) >= 2:
                potential_qtys = [n for n in valid_prices[:3] if n < 100 and n.is_integer()]
                if potential_qtys:
                    qty = potential_qtys[0]
                    valid_prices.remove(qty)
                else:
                    qty = 1.0
                mrp = valid_prices[-1]
            elif len(valid_prices) == 1:
                mrp = valid_prices[0]
                
            if part_no:
                parsed_items.append({
                    "part_number": part_no,
                    "qty": int(qty),
                    "mrp": float(mrp),
                    "description": clean_desc
                })
                
        return parsed_items
    except Exception:
        return []
