import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)

def safe_float(value, default=0.0):
    """
    Safely convert any value to float.
    Handles: None, empty string, "null", actual numbers
    """
    if value is None or value == "" or value == "null":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        logger.warning(f"Could not convert '{value}' to float, using default {default}")
        return default


def extract_gstr2b_data(json_data, period_label):
    """
    Parses GSTR-2B JSON based on ACTUAL API structure.
    Tax data is at invoice level: val, txval, igst, cgst, sgst, cess
    """
    b2b_rows = []
    cdnr_rows = []

    # Navigate to the actual data structure
    # Response: data -> data -> data -> docdata
    try:
        # Handle nested "data" keys
        actual_data = json_data
        while "data" in actual_data and isinstance(actual_data["data"], dict):
            actual_data = actual_data["data"]
        
        docdata = actual_data.get("docdata")
        if not docdata:
            logger.warning(f"No docdata found for period {period_label}")
            return [], []
    except (KeyError, TypeError) as e:
        logger.error(f"Error navigating to docdata: {e}")
        return [], []

    logger.info(f"Processing GSTR-2B data for {period_label}")

    # 2. PROCESS B2B
    b2b_data = docdata.get("b2b", [])
    if isinstance(b2b_data, dict):
        b2b_data = list(b2b_data.values())

    if isinstance(b2b_data, list):
        logger.info(f"Found {len(b2b_data)} B2B suppliers")
        
        for supplier in b2b_data:
            if not isinstance(supplier, dict):
                continue
                
            ctin = supplier.get("ctin", "")
            trdnm = supplier.get("trdnm", "")
            
            invoices = supplier.get("inv", [])
            if isinstance(invoices, dict):
                invoices = list(invoices.values())
            
            for inv in invoices:
                if not isinstance(inv, dict):
                    continue
                
                # Get invoice data - ALL AT INVOICE LEVEL (no items array)
                inum = inv.get("inum", "")
                dt = inv.get("dt", "")
                
                # Tax values are directly in the invoice object
                val = safe_float(inv.get("val"))          # Gross amount
                txval = safe_float(inv.get("txval"))      # Taxable value
                igst = safe_float(inv.get("igst"))        # IGST
                cgst = safe_float(inv.get("cgst"))        # CGST
                sgst = safe_float(inv.get("sgst"))        # SGST
                cess = safe_float(inv.get("cess"))        # Cess
                
                b2b_rows.append({
                    "GSTIN/UIN": ctin,
                    "Supplier": trdnm,
                    "Invoice": inum,
                    "Date": dt,
                    "Gross Amt": val,
                    "Taxable": round(txval, 2),
                    "IGST": round(igst, 2),
                    "CGST": round(cgst, 2),
                    "SGST": round(sgst, 2),
                    "Cess": round(cess, 2),
                    "Type": "B2B"
                })

    # 3. PROCESS B2BA (Amended B2B invoices)
    b2ba_data = docdata.get("b2ba", [])
    if isinstance(b2ba_data, dict):
        b2ba_data = list(b2ba_data.values())

    if isinstance(b2ba_data, list):
        logger.info(f"Found {len(b2ba_data)} B2BA suppliers")
        
        for supplier in b2ba_data:
            if not isinstance(supplier, dict):
                continue
                
            ctin = supplier.get("ctin", "")
            trdnm = supplier.get("trdnm", "")
            
            invoices = supplier.get("inv", [])
            if isinstance(invoices, dict):
                invoices = list(invoices.values())
            
            for inv in invoices:
                if not isinstance(inv, dict):
                    continue
                
                # Get invoice data
                inum = inv.get("inum", "")
                dt = inv.get("dt", "")
                
                # Tax values at invoice level
                val = safe_float(inv.get("val"))
                txval = safe_float(inv.get("txval"))
                igst = safe_float(inv.get("igst"))
                cgst = safe_float(inv.get("cgst"))
                sgst = safe_float(inv.get("sgst"))
                cess = safe_float(inv.get("cess"))
                
                b2b_rows.append({
                    "GSTIN/UIN": ctin,
                    "Supplier": trdnm,
                    "Invoice": inum,
                    "Date": dt,
                    "Gross Amt": val,
                    "Taxable": round(txval, 2),
                    "IGST": round(igst, 2),
                    "CGST": round(cgst, 2),
                    "SGST": round(sgst, 2),
                    "Cess": round(cess, 2),
                    "Type": "B2BA"
                })

    # 4. PROCESS CDNR (Credit/Debit Notes)
    cdnr_data = docdata.get("cdnr", [])
    if isinstance(cdnr_data, dict):
        cdnr_data = list(cdnr_data.values())
    
    if isinstance(cdnr_data, list):
        logger.info(f"Found {len(cdnr_data)} CDNR suppliers")
        
        for supplier in cdnr_data:
            if not isinstance(supplier, dict):
                continue
                
            ctin = supplier.get("ctin", "")
            trdnm = supplier.get("trdnm", "")
            
            notes = supplier.get("nt", [])
            if isinstance(notes, dict):
                notes = list(notes.values())
            
            for note in notes:
                if not isinstance(note, dict):
                    continue
                
                # Get note data - structure is: ntnum (note number), not nt_num
                nt_num = note.get("ntnum", "") or note.get("nt_num", "")
                dt = note.get("dt", "")
                
                # Tax values at note level
                val = safe_float(note.get("val"))
                txval = safe_float(note.get("txval"))
                igst = safe_float(note.get("igst"))
                cgst = safe_float(note.get("cgst"))
                sgst = safe_float(note.get("sgst"))
                cess = safe_float(note.get("cess"))
                
                cdnr_rows.append({
                    "GSTIN/UIN": ctin,
                    "Supplier": trdnm,
                    "Invoice": nt_num,
                    "Date": dt,
                    "Gross Amt": val,
                    "Taxable": round(txval, 2),
                    "IGST": round(igst, 2),
                    "CGST": round(cgst, 2),
                    "SGST": round(sgst, 2),
                    "Cess": round(cess, 2),
                    "Type": "CDNR"
                })

    # 5. PROCESS CDNRA (Amended Credit/Debit Notes)
    cdnra_data = docdata.get("cdnra", [])
    if isinstance(cdnra_data, dict):
        cdnra_data = list(cdnra_data.values())
    
    if isinstance(cdnra_data, list):
        logger.info(f"Found {len(cdnra_data)} CDNRA suppliers")
        
        for supplier in cdnra_data:
            if not isinstance(supplier, dict):
                continue
                
            ctin = supplier.get("ctin", "")
            trdnm = supplier.get("trdnm", "")
            
            notes = supplier.get("nt", [])
            if isinstance(notes, dict):
                notes = list(notes.values())
            
            for note in notes:
                if not isinstance(note, dict):
                    continue
                
                nt_num = note.get("ntnum", "") or note.get("nt_num", "")
                dt = note.get("dt", "")
                
                val = safe_float(note.get("val"))
                txval = safe_float(note.get("txval"))
                igst = safe_float(note.get("igst"))
                cgst = safe_float(note.get("cgst"))
                sgst = safe_float(note.get("sgst"))
                cess = safe_float(note.get("cess"))
                
                cdnr_rows.append({
                    "GSTIN/UIN": ctin,
                    "Supplier": trdnm,
                    "Invoice": nt_num,
                    "Date": dt,
                    "Gross Amt": val,
                    "Taxable": round(txval, 2),
                    "IGST": round(igst, 2),
                    "CGST": round(cgst, 2),
                    "SGST": round(sgst, 2),
                    "Cess": round(cess, 2),
                    "Type": "CDNRA"
                })

    logger.info(f"Extracted {len(b2b_rows)} B2B/B2BA rows and {len(cdnr_rows)} CDNR/CDNRA rows for {period_label}")
    
    # Final check
    if b2b_rows:
        sample_row = b2b_rows[0]
        logger.info(f"Sample B2B row: Taxable={sample_row['Taxable']}, IGST={sample_row['IGST']}, CGST={sample_row['CGST']}, SGST={sample_row['SGST']}")
    
    return b2b_rows, cdnr_rows


def generate_excel_bytes(b2b_rows, cdnr_rows):
    """
    Generate Excel file with B2B and CDNR data
    """
    df_b2b = pd.DataFrame(b2b_rows)
    df_cdnr = pd.DataFrame(cdnr_rows)

    # Define columns
    b2b_cols = ["GSTIN/UIN", "Supplier", "Invoice", "Date", "Gross Amt", 
                "Taxable", "IGST", "CGST", "SGST", "Cess", "Type"]
    cdnr_cols = ["GSTIN/UIN", "Supplier", "Invoice", "Date", "Gross Amt", 
                 "Taxable", "IGST", "CGST", "SGST", "Cess", "Type"]
    
    # Columns that MUST be numbers
    numeric_fields = ["Gross Amt", "Taxable", "IGST", "CGST", "SGST", "Cess"]

    # --- PROCESS B2B ---
    if not df_b2b.empty:
        # Ensure all standard columns exist
        for col in b2b_cols:
            if col not in df_b2b.columns:
                df_b2b[col] = None
        
        # Enforce Numeric Types
        for col in numeric_fields:
            if col in df_b2b.columns:
                df_b2b[col] = pd.to_numeric(df_b2b[col], errors='coerce').fillna(0.0)
        
        df_b2b = df_b2b[b2b_cols]
    else:
        df_b2b = pd.DataFrame(columns=b2b_cols)

    # --- PROCESS CDNR ---
    if not df_cdnr.empty:
        for col in cdnr_cols:
            if col not in df_cdnr.columns:
                df_cdnr[col] = None
            
        # Enforce Numeric Types
        for col in numeric_fields:
            if col in df_cdnr.columns:
                df_cdnr[col] = pd.to_numeric(df_cdnr[col], errors='coerce').fillna(0.0)
                
        df_cdnr = df_cdnr[cdnr_cols]
    else:
        df_cdnr = pd.DataFrame(columns=cdnr_cols)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_b2b.to_excel(writer, sheet_name='B2B_Data', index=False)
        df_cdnr.to_excel(writer, sheet_name='CDNR_Data', index=False)
    
    output.seek(0)
    return output