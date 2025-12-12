import pandas as pd
import pdfplumber
import re
from typing import Tuple, List, Dict

def parse_file(path: str, source: str):
    """
    Returns: (rows: List[Dict], summary: Dict)
    rows: invoice-level canonical rows with keys:
        invoice_no, invoice_date, taxable_value, igst, cgst, sgst, doc_type, pos, note_type, reference_no
    summary: totals
    """
    ext = path.split('.')[-1].lower()
    if ext in ['xls','xlsx','csv']:
        return parse_excel(path, source)
    if ext == 'pdf':
        return parse_pdf(path, source)
    raise ValueError("Unsupported file type")

def parse_pdf(path: str, source: str):
    rows = []
    summary = {"total_taxable": 0, "igst": 0, "cgst": 0, "sgst": 0, "cess": 0, "total_records": 0}
    found_main_table = False
    
    def clean_num(val):
        if not val or val == '-' or val == '':
            return 0
        try:
            # Remove common non-numeric characters
            cleaned = str(val).replace(',', '').replace('Γé╣', '').replace('₹', '').strip()
            # Check if it's actually a number
            if not cleaned or not any(c.isdigit() for c in cleaned):
                return 0
            return float(cleaned)
        except (ValueError, AttributeError):
            return 0
    
    with pdfplumber.open(path) as pdf:
        # Only process first page for summary
        for page in pdf.pages[:1]:
            tables = page.extract_tables()
            
            # Find the largest table with tax data (main summary table)
            main_table = None
            max_data_rows = 0
            
            for table in tables:
                if not table or len(table) < 2:
                    continue
                
                headers = [str(h).strip().lower() if h else "" for h in table[0]]
                has_value = any('value' in h or 'taxable' in h for h in headers)
                has_tax = any('tax' in h or 'igst' in h or 'cgst' in h or 'sgst' in h for h in headers)
                
                if (has_value or has_tax) and len(table) > max_data_rows:
                    max_data_rows = len(table)
                    main_table = table
            
            if not main_table:
                continue
            
            # Process only the main table
            table = main_table
            headers = [str(h).strip().lower() if h else "" for h in table[0]]
                
            # Find column indices
            desc_idx = next((i for i, h in enumerate(headers) if 'description' in h or 'nature' in h or 'detail' in h), 0)
            records_idx = next((i for i, h in enumerate(headers) if 'record' in h), -1)
            value_idx = next((i for i, h in enumerate(headers) if 'value' in h or 'taxable' in h), -1)
            igst_idx = next((i for i, h in enumerate(headers) if 'integrated' in h or 'igst' in h), -1)
            cgst_idx = next((i for i, h in enumerate(headers) if 'central' in h or 'cgst' in h), -1)
            sgst_idx = next((i for i, h in enumerate(headers) if 'state' in h or 'sgst' in h or 'ut' in h), -1)
            
            # Parse data rows
            for row in table[1:]:
                try:
                    if not row or not any(row):
                        continue
                    
                    desc = str(row[desc_idx] if desc_idx < len(row) else "").strip()
                    if not desc:
                        continue
                    
                    # Skip single letter headers like 'A', 'D'
                    is_header_row = len(desc) < 5 and desc.isupper()
                    if is_header_row:
                        continue
                    
                    record_count = clean_num(row[records_idx]) if records_idx >= 0 and records_idx < len(row) else 0
                    taxable = clean_num(row[value_idx]) if value_idx >= 0 and value_idx < len(row) else 0
                    igst = clean_num(row[igst_idx]) if igst_idx >= 0 and igst_idx < len(row) else 0
                    cgst = clean_num(row[cgst_idx]) if cgst_idx >= 0 and cgst_idx < len(row) else 0
                    sgst = clean_num(row[sgst_idx]) if sgst_idx >= 0 and sgst_idx < len(row) else 0
                    
                    # Include row if it has any numeric data
                    if taxable > 0 or igst > 0 or cgst > 0 or sgst > 0 or record_count > 0:
                        rows.append({
                            "invoice_no": desc,
                            "record_count": int(record_count),
                            "taxable_value": taxable,
                            "igst": igst,
                            "cgst": cgst,
                            "sgst": sgst,
                            "cess": 0
                        })
                        
                        # For GSTR-1: Use ONLY the "Total" row for summary
                        # For GSTR-3B: Sum all data rows
                        if 'total' in desc.lower() and record_count > 50:  # Total row has high record count
                            summary["total_records"] = int(record_count)
                            summary["total_taxable"] = taxable
                            summary["igst"] = igst
                            summary["cgst"] = cgst
                            summary["sgst"] = sgst
                        elif 'total' not in desc.lower():  # For GSTR-3B rows
                            summary["total_taxable"] += taxable
                            summary["igst"] += igst
                            summary["cgst"] += cgst
                            summary["sgst"] += sgst
                except Exception as e:
                    print(f"DEBUG: Skipping row due to error: {e}")
                    continue
    
    print(f"DEBUG PDF Parser: Extracted {len(rows)} rows, Records:{summary['total_records']}, Taxable:{summary['total_taxable']}")
    return rows, summary

# parse_excel: easier - expect tables and column names
def parse_excel(path: str, source: str):
    df = pd.read_excel(path, sheet_name=0)
    print(f"DEBUG Parser: Loaded {len(df)} rows from {source}")
    print(f"DEBUG Parser: Columns: {list(df.columns)}")
    
    # map typical column names (attempt mapping heuristics)
    L = df.columns
    def find_col(possible):
        # First try exact match (case-insensitive)
        for name in possible:
            for c in L:
                if str(c).strip().lower() == name.lower():
                    return c
        # Then try partial match
        for name in possible:
            for c in L:
                if name.lower() in str(c).strip().lower():
                    return c
        return None

    invoice_col = find_col(['Document Type','invoice', 'document', 'doc no', 'document number', 'bill', 'nature of supplies'])
    record_count_col = find_col(['No. of records','no of records', 'number of records', 'count', 'no. of records'])
    taxable_col = find_col(['taxable', 'value', 'amount', 'net value', 'total'])
    igst_col = find_col(['Integrated Tax','igst', 'integrated tax', 'integrated gst'])
    cgst_col = find_col(['Central Tax','cgst', 'central tax', 'central gst'])
    sgst_col = find_col(['State/UT Tax','sgst', 'state/ut tax', 'state tax', 'state gst'])
    cess_col = find_col(['cess','Cess'])
    gstin_col = find_col(['gstin', 'gst no', 'gst number', 'recipient gstin'])
    
    print(f"DEBUG Parser: Mapped columns - invoice:{invoice_col}, records:{record_count_col}, taxable:{taxable_col}, igst:{igst_col}, cgst:{cgst_col}, sgst:{sgst_col}")
    
    # Print first 3 rows for debugging
    if len(df) > 0:
        print(f"DEBUG Parser: First row data: {df.iloc[0].to_dict()}")

    rows = []
    skip_keywords = ['total', 'summary', 'grand']
    
    if invoice_col or taxable_col:
        for idx, r in df.iterrows():
            inv_no = str(r.get(invoice_col, "") if invoice_col else f"ROW_{idx}").strip()
            taxable = 0
            
            # Try to get taxable value
            if taxable_col:
                try:
                    taxable = float(r.get(taxable_col, 0) or 0)
                except:
                    taxable = 0
            
            # Get record count if available
            record_count = 0
            if record_count_col:
                try:
                    record_count = int(r.get(record_count_col, 0) or 0)
                except:
                    record_count = 0
            
            # Skip completely empty rows
            if not inv_no or inv_no == "nan":
                continue
            
            # Skip only grand total rows
            inv_lower = inv_no.lower()
            if any(keyword in inv_lower for keyword in skip_keywords):
                continue
            
            # For GSTR-1 format: Keep rows with either taxable value OR record count
            if taxable == 0 and record_count == 0:
                continue
                
            rows.append({
                "invoice_no": inv_no,
                "record_count": record_count,
                "invoice_date": str(r.get('Invoice Date', "")),
                "taxable_value": taxable,
                "igst": float(r.get(igst_col, 0) or 0) if igst_col else 0,
                "cgst": float(r.get(cgst_col, 0) or 0) if cgst_col else 0,
                "sgst": float(r.get(sgst_col, 0) or 0) if sgst_col else 0,
                "cess": float(r.get(cess_col, 0) or 0) if cess_col else 0,
                "gstin": str(r.get(gstin_col, "") if gstin_col else "").strip(),
                "doc_type": "GSTR1_CATEGORY",
                "pos": None
            })
    
    print(f"DEBUG Parser: Extracted {len(rows)} valid rows")
    
    # Calculate summary from extracted rows (more accurate than raw column sum)
    total_records = sum(r.get('record_count', 0) for r in rows)
    summary = {
        "total_taxable": sum(r.get('taxable_value', 0) for r in rows),
        "igst": sum(r.get('igst', 0) for r in rows),
        "cgst": sum(r.get('cgst', 0) for r in rows),
        "sgst": sum(r.get('sgst', 0) for r in rows),
        "cess": sum(r.get('cess', 0) for r in rows),
        "total_records": total_records
    }
    
    print(f"DEBUG Parser: Summary - Records:{total_records}, Taxable:{summary['total_taxable']}, IGST:{summary['igst']}, CGST:{summary['cgst']}, SGST:{summary['sgst']}")
    return rows, summary
