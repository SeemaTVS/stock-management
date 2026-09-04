def parse_dealer_bill(scanned_text):
    parsed_items = []
    if not scanned_text:
        return parsed_items
        
    lines = [l.strip() for l in scanned_text.split('\n') if l.strip()]
    current_item = None
    
    for line in lines:
        line_upper = line.upper()
        
        match_serial = re.match(r'^(\d{1,2})\s+([A-Z0-9\-]{5,12})', line)
        if match_serial and int(match_serial.group(1)) <= 30:
            if current_item and current_item.get("part_number") and current_item.get("mrp") > 0:
                parsed_items.append(current_item)
                
            part_no = match_serial.group(2)
            remaining_text = line[len(match_serial.group(0)):].strip()
            current_item = {
                "part_number": part_no,
                "description_lines": [remaining_text] if remaining_text else [],
                "qty": 1.0,
                "mrp": 0.0
            }
        elif current_item is not None:
            if any(w in line_upper for w in ['TOTAL', 'CGST', 'SGST', 'INVOICE', 'GSTIN']):
                if current_item.get("part_number") and current_item.get("mrp") > 0:
                    parsed_items.append(current_item)
                current_item = None
                continue
                
            nums = re.findall(r'\b\d+(?:\.\d{2})?\b', line)
            if nums:
                for n_str in nums:
                    val = float(n_str)
                    if val < 50 and current_item["qty"] == 1.0:
                        current_item["qty"] = val
                    elif val > 50:
                        current_item["mrp"] = val
            
            if not re.match(r'^[\d\.\s]+$', line):
                current_item["description_lines"].append(line)

    if current_item and current_item.get("part_number") and current_item.get("mrp") > 0:
        parsed_items.append(current_item)

    final_cleaned_items = []
    for item in parsed_items:
        raw_desc = " ".join(item["description_lines"])
        
        # Split into individual words, then keep ONLY pure alphabetic words (ignoring numbers, slashes, and alphanumeric tokens/codes)
        words = raw_desc.split()
        alpha_words = [w for w in words if w.isalpha() and len(w) > 1]
        
        # Fallback if no clean words remain
        clean_desc = " ".join(alpha_words).strip()
        if not clean_desc:
            clean_desc = f"Part {item['part_number']}"
            
        final_cleaned_items.append({
            "part_number": item["part_number"].strip().upper(),
            "qty": int(item["qty"]),
            "mrp": float(item["mrp"]),
            "description": clean_desc
        })
        
    return final_cleaned_items
