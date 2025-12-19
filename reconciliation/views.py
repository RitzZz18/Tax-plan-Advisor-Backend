from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse

import pandas as pd
import numpy as np
from datetime import datetime
import io
import re

# ---------------------------
# CONSTANTS
# ---------------------------
REQUIRED_COLUMNS = [
    "GSTIN/UIN", "Supplier", "Invoice", "Date",
    "Gross Amt", "Taxable", "IGST", "SGST", "CGST", "Cess", "Type"
]

NUMERIC_COLUMNS = ["Gross Amt", "Taxable", "IGST", "SGST", "CGST", "Cess"]

# ---------------------------
# HELPER FUNCTIONS
# ---------------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace, handle duplicates, and normalize basic headers."""
    # 1. Clean column names (strip whitespace)
    df.columns = df.columns.astype(str).str.strip()
    
    # 2. Handle Duplicates
    if not df.columns.is_unique:
        counts = {}
        new_columns = []
        for col in df.columns:
            if col in counts:
                counts[col] += 1
                new_columns.append(f"{col}_{counts[col]}") 
            else:
                counts[col] = 0
                new_columns.append(col)
        df.columns = new_columns
    return df

def validate_structure(df: pd.DataFrame, filename: str):
    # 'Type' is optional in books validation
    required_check = [c for c in REQUIRED_COLUMNS if c != "Type"]
    
    # Check if critical columns exist
    missing = [col for col in required_check if col not in df.columns]
    
    # Auto-fill Cess if missing (common issue)
    if "Cess" in missing:
        df["Cess"] = 0
        if "Cess" in missing: missing.remove("Cess")
        
    if missing:
        return False, f"Error in {filename}: Missing columns: {', '.join(missing)}", df
    return True, "", df

def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """Converts numeric columns, cleans strings, parses dates."""
    # 1. Numeric Conversion
    for col in NUMERIC_COLUMNS:
        if col not in df.columns:
            df[col] = 0
        # Force numeric, coerce errors to NaN, then fill with 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 2. Clean Invoice
    if "Invoice" in df.columns:
        df["Invoice"] = (
            df["Invoice"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True) 
            .replace(["nan", "None", "NaN"], "")
        )
        df["Invoice_Clean"] = df["Invoice"].str.strip().str.upper()

    # 3. Clean GSTIN
    if "GSTIN/UIN" in df.columns:
        df["GSTIN/UIN"] = df["GSTIN/UIN"].astype(str).replace(["nan", "None"], "")
        df["GSTIN_Clean"] = df["GSTIN/UIN"].str.strip().str.upper()

    # 4. Date parsing
    # Try multiple formats if standard fails
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")

    # 5. Handle Type (B2B vs CDNR)
    if "Type" not in df.columns:
        df["Type"] = "B2B"
    
    df["Type"] = df["Type"].astype(str).str.strip().str.upper()
    
    # Normalize common variations for Credit Notes
    cdnr_pattern = r"(CDNR|CREDIT|CR\.|DEBIT|DR\.|NOTE)"
    df.loc[df["Type"].str.contains(cdnr_pattern, regex=True, na=False), "Type"] = "CDNR"
    df.loc[df["Type"] != "CDNR", "Type"] = "B2B"

    return df

def get_target_periods(fy_string: str, period_type: str, selected_period: str):
    try:
        start_year = int(fy_string.split("-")[0])
        end_year = int(fy_string.split("-")[1])
    except:
        start_year = datetime.now().year
        end_year = start_year + 1

    target_dates = []
    period_label = ""

    if period_type == "Monthly":
        month_map = {
            "April": 4, "May": 5, "June": 6, "July": 7, "August": 8, "September": 9,
            "October": 10, "November": 11, "December": 12, "January": 1, "February": 2, "March": 3
        }
        m_num = month_map.get(selected_period, 4)
        y_num = start_year if m_num >= 4 else end_year
        target_dates = [(m_num, y_num)]
        period_label = f"{selected_period} {y_num}"

    elif period_type == "Quarterly":
        if selected_period == "Q1 (Apr-Jun)":
            target_dates = [(4, start_year), (5, start_year), (6, start_year)]
        elif selected_period == "Q2 (Jul-Sep)":
            target_dates = [(7, start_year), (8, start_year), (9, start_year)]
        elif selected_period == "Q3 (Oct-Dec)":
            target_dates = [(10, start_year), (11, start_year), (12, start_year)]
        elif selected_period == "Q4 (Jan-Mar)":
            target_dates = [(1, end_year), (2, end_year), (3, end_year)]
        period_label = f"{selected_period} ({fy_string})"
    
    elif period_type == "Yearly":
        # April to December (Start Year)
        target_dates.extend([(m, start_year) for m in range(4, 13)])
        # January to March (End Year)
        target_dates.extend([(m, end_year) for m in range(1, 4)])
        period_label = f"Financial Year {fy_string}"

    return target_dates, period_label

def values_match_within_tolerance(val1, val2, tolerance):
    return abs(val1 - val2) <= tolerance

# ---------------------------
# CORE RECONCILIATION LOGIC
# ---------------------------
def run_reconciliation(df_2b, df_books, target_dates, tolerance=1):
    def is_in_period(df):
        valid = set(target_dates)
        return df["Date"].apply(
            lambda d: (d.month, d.year) in valid if pd.notnull(d) else False
        )

    def safe_str(v):
        s = str(v)
        return "" if s in ["nan", "None"] else s
    
    def coalesce_row(r, cols):
        for c in cols:
            if c in r.index and pd.notnull(r[c]) and str(r[c]).strip() not in ["", "nan"]:
                return r[c]
        return ""

    # Filter by Period
    df_books_current = df_books[is_in_period(df_books)].copy()
    df_2b_current = df_2b[is_in_period(df_2b)].copy()

    df_books_out = df_books[~is_in_period(df_books)].copy()
    df_2b_out = df_2b[~is_in_period(df_2b)].copy()

    df_out_of_period = pd.concat([
        df_books_out.assign(Source="Books"), 
        df_2b_out.assign(Source="GSTR-2B")
    ], ignore_index=True)

    # --- MATCHING LOGIC ---
    merged_step1 = pd.merge(
        df_2b_current,
        df_books_current,
        on=["GSTIN_Clean", "Invoice_Clean"],
        how="outer",
        suffixes=("_2b", "_books"),
        indicator=True,
    )

    exact_key_match = merged_step1[merged_step1["_merge"] == "both"]
    leftover_2b = merged_step1[merged_step1["_merge"] == "left_only"]
    leftover_books = merged_step1[merged_step1["_merge"] == "right_only"]

    results_matched = []
    results_mismatch_probable = []
    results_invoice_mismatch = []
    results_only_2b = []
    results_only_books = []

    # 1. Exact Match Processing
    for _, row in exact_key_match.iterrows():
        is_val_match = True
        for col in NUMERIC_COLUMNS:
            val_2b = row.get(f"{col}_2b", 0)
            val_books = row.get(f"{col}_books", 0)
            if not values_match_within_tolerance(val_2b, val_books, tolerance):
                is_val_match = False
                break
        
        base_data = {
            "GSTIN": safe_str(row.get("GSTIN/UIN_2b")),
            "Supplier": safe_str(row.get("Supplier_2b")),
            "Invoice_2B": safe_str(row.get("Invoice_Original_2B_2b") if "Invoice_Original_2B_2b" in row else row.get("Invoice_2b")),
            "Invoice_Books": safe_str(row.get("Invoice_Original_Books_books") if "Invoice_Original_Books_books" in row else row.get("Invoice_books")),
            "Date_2B": row.get("Date_2b"),
            "Date_Books": row.get("Date_books"),
            "Taxable_2B": row.get("Taxable_2b", 0),
            "Taxable_Books": row.get("Taxable_books", 0),
            "IGST_2B": row.get("IGST_2b", 0),
            "IGST_Books": row.get("IGST_books", 0),
            "CGST_2B": row.get("CGST_2b", 0),
            "CGST_Books": row.get("CGST_books", 0),
            "SGST_2B": row.get("SGST_2b", 0),
            "SGST_Books": row.get("SGST_books", 0),
            "Cess_2B": row.get("Cess_2b", 0),
            "Cess_Books": row.get("Cess_books", 0),
            "Gross_2B": row.get("Gross Amt_2b", 0),
            "Gross_Books": row.get("Gross Amt_books", 0),
            "Gross_Diff": round(abs(row.get("Gross Amt_2b", 0) - row.get("Gross Amt_books", 0)), 2),
            "Type": row.get("Type_2b", "B2B")
        }

        if is_val_match:
            results_matched.append(base_data)
        else:
            results_mismatch_probable.append(base_data)

    # 2. Fuzzy Match Logic (Simplified for brevity, same as before)
    cols_2b = {col: col.replace("_2b", "") for col in leftover_2b.columns if "_2b" in col}
    cols_2b.update({"GSTIN_Clean": "GSTIN_Clean", "Invoice_Clean": "Invoice_Original_2B"})
    unique_cols_2b = list(dict.fromkeys(list(cols_2b.keys()) + ["GSTIN_Clean"]))
    df_2b_candidate = leftover_2b[unique_cols_2b].rename(columns=cols_2b)

    cols_books = {col: col.replace("_books", "") for col in leftover_books.columns if "_books" in col}
    cols_books.update({"GSTIN_Clean": "GSTIN_Clean", "Invoice_Clean": "Invoice_Original_Books"})
    unique_cols_books = list(dict.fromkeys(list(cols_books.keys()) + ["GSTIN_Clean"]))
    df_books_candidate = leftover_books[unique_cols_books].rename(columns=cols_books)

    unmatched_2b_indices = set(df_2b_candidate.index)
    unmatched_books_indices = set(df_books_candidate.index)

    # Fuzzy matching loop
    for idx_2b, row_2b in df_2b_candidate.iterrows():
        possible_books = df_books_candidate[df_books_candidate["GSTIN_Clean"] == row_2b["GSTIN_Clean"]]
        match_found = False

        for idx_books, row_books in possible_books.iterrows():
            if idx_books not in unmatched_books_indices: continue

            if (values_match_within_tolerance(row_2b.get("Taxable", 0), row_books.get("Taxable", 0), tolerance)
                and values_match_within_tolerance(row_2b.get("IGST", 0), row_books.get("IGST", 0), tolerance)):
                
                gross_match = values_match_within_tolerance(row_2b.get("Gross Amt", 0), row_books.get("Gross Amt", 0), tolerance)
                
                base_data = {
                    "GSTIN": safe_str(coalesce_row(row_2b, ["GSTIN_Clean", "GSTIN/UIN"])),
                    "Supplier": safe_str(row_2b.get("Supplier", "")),
                    "Invoice_2B": safe_str(row_2b.get("Invoice_Original_2B", row_2b.get("Invoice", ""))),
                    "Invoice_Books": safe_str(row_books.get("Invoice_Original_Books", row_books.get("Invoice", ""))),
                    "Date_2B": row_2b.get("Date"),
                    "Date_Books": row_books.get("Date"),
                    "Taxable_2B": row_2b.get("Taxable", 0),
                    "Taxable_Books": row_books.get("Taxable", 0),
                    "IGST_2B": row_2b.get("IGST", 0),
                    "IGST_Books": row_books.get("IGST", 0),
                    "CGST_2B": row_2b.get("CGST", 0),
                    "CGST_Books": row_books.get("CGST", 0),
                    "SGST_2B": row_2b.get("SGST", 0),
                    "SGST_Books": row_books.get("SGST", 0),
                    "Cess_2B": row_2b.get("Cess", 0),
                    "Cess_Books": row_books.get("Cess", 0),
                    "Gross_2B": row_2b.get("Gross Amt", 0),
                    "Gross_Books": row_books.get("Gross Amt", 0),
                    "Gross_Diff": round(abs(row_2b.get("Gross Amt", 0) - row_books.get("Gross Amt", 0)), 2),
                    "Type": row_2b.get("Type", "B2B")
                }

                if gross_match: results_invoice_mismatch.append(base_data)
                else: results_mismatch_probable.append(base_data)

                unmatched_2b_indices.discard(idx_2b)
                unmatched_books_indices.discard(idx_books)
                break

    # 3. Handle Orphans
    for idx in unmatched_2b_indices:
        row = df_2b_candidate.loc[idx]
        results_only_2b.append({
            "GSTIN": safe_str(row.get("GSTIN_Clean")),
            "Supplier": safe_str(row.get("Supplier")),
            "Invoice_2B": safe_str(row.get("Invoice_Original_2B", row.get("Invoice"))),
            "Invoice_Books": "",
            "Date_2B": row.get("Date"),
            "Date_Books": "",
            "Taxable_2B": row.get("Taxable", 0),
            "Taxable_Books": 0,
            "IGST_2B": row.get("IGST", 0),
            "IGST_Books": 0,
            "CGST_2B": row.get("CGST", 0),
            "CGST_Books": 0,
            "SGST_2B": row.get("SGST", 0),
            "SGST_Books": 0,
            "Cess_2B": row.get("Cess", 0),
            "Cess_Books": 0,
            "Gross_2B": row.get("Gross Amt", 0),
            "Gross_Books": 0,
            "Gross_Diff": 0,
            "Type": row.get("Type", "B2B")
        })

    for idx in unmatched_books_indices:
        row = df_books_candidate.loc[idx]
        results_only_books.append({
            "GSTIN": safe_str(row.get("GSTIN_Clean")),
            "Supplier": safe_str(row.get("Supplier")),
            "Invoice_2B": "",
            "Invoice_Books": safe_str(row.get("Invoice_Original_Books", row.get("Invoice"))),
            "Date_2B": "",
            "Date_Books": row.get("Date"),
            "Taxable_2B": 0,
            "Taxable_Books": row.get("Taxable", 0),
            "IGST_2B": 0,
            "IGST_Books": row.get("IGST", 0),
            "CGST_2B": 0,
            "CGST_Books": row.get("CGST", 0),
            "SGST_2B": 0,
            "SGST_Books": row.get("SGST", 0),
            "Cess_2B": 0,
            "Cess_Books": row.get("Cess", 0),
            "Gross_2B": 0,
            "Gross_Books": row.get("Gross Amt", 0),
            "Gross_Diff": 0,
            "Type": row.get("Type", "B2B")
        })

    # Convert to DataFrames
    return {
        "matched": pd.DataFrame(results_matched),
        "mismatch_probable": pd.DataFrame(results_mismatch_probable),
        "invoice_mismatch": pd.DataFrame(results_invoice_mismatch),
        "only_2b": pd.DataFrame(results_only_2b),
        "only_books": pd.DataFrame(results_only_books),
        "out_of_period": pd.DataFrame(df_out_of_period)
    }

# ---------------------------
# EXCEL GENERATION
# ---------------------------
def generate_advanced_excel(results_dict, period_label):
    output = io.BytesIO()
    
    totals = results_dict.get("original_totals", {})
    # Totals Logic
    b2b_2b = totals.get("b2b_tax_2b", 0)
    cdnr_2b = totals.get("cdnr_tax_2b", 0)
    total_2b = b2b_2b + cdnr_2b
    
    b2b_books = totals.get("b2b_tax_books", 0)
    cdnr_books = totals.get("cdnr_tax_books", 0)
    total_books = b2b_books + cdnr_books 
    
    tax_difference = round(total_2b - total_books, 2)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        
        # --- GLOBAL STYLES ---
        # 1. Main Title
        header_fmt = workbook.add_format({
            'bold': True, 'font_size': 16, 'font_color': '#FFFFFF', 
            'bg_color': '#1E3A8A', 'align': 'center', 'valign': 'vcenter', 'border': 1
        })
        
        # 2. Section Headers (Light Blue)
        subheader_fmt = workbook.add_format({
            'bold': True, 'font_size': 12, 'font_color': '#1E3A8A', 
            'bg_color': '#DBEAFE', 'align': 'left', 'valign': 'vcenter', 'border': 1
        })
        
        # 3. Data Labels
        label_fmt = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': '#334155', 
            'bg_color': '#F8FAFC', 'align': 'left', 'valign': 'vcenter', 'border': 1
        })

        # 4. Currency Values
        curr_fmt = workbook.add_format({
            'num_format': '₹#,##0.00', 'bold': True, 'font_size': 11, 
            'bg_color': '#FFFFFF', 'align': 'right', 'border': 1
        })

        # 5. Count Values (Integrals - NO Currency)
        count_fmt = workbook.add_format({
            'num_format': '0', 'bold': True, 'font_size': 11, 
            'bg_color': '#FFFFFF', 'align': 'center', 'border': 1
        })

        # 6. Difference Formatting (Red/Green)
        diff_pos_fmt = workbook.add_format({
            'num_format': '₹#,##0.00', 'bold': True, 'font_size': 11, 'font_color': '#16A34A', 
            'bg_color': '#F0FDF4', 'align': 'right', 'border': 1
        })
        diff_neg_fmt = workbook.add_format({
            'num_format': '₹#,##0.00', 'bold': True, 'font_size': 11, 'font_color': '#DC2626', 
            'bg_color': '#FEF2F2', 'align': 'right', 'border': 1
        })

        # 7. Table Header (Dark Grey)
        table_header_fmt = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': '#FFFFFF', 
            'bg_color': '#475569', 'align': 'center', 'valign': 'vcenter', 'border': 1
        })
        
        # --- SHEET 1: EXECUTIVE SUMMARY ---
        ws = workbook.add_worksheet("Executive Summary")
        writer.sheets["Executive Summary"] = ws
        
        # Set Column Widths
        ws.set_column('A:A', 2)   
        ws.set_column('B:B', 35)  
        ws.set_column('C:C', 20)  
        ws.set_column('D:D', 20)  
        ws.set_column('E:E', 30)  
        
        # Title
        ws.merge_range('B2:E2', f'GST RECONCILIATION - {period_label}', header_fmt)
        
        # -- Financial Overview --
        row = 4
        ws.merge_range(row, 1, row, 4, 'FINANCIAL OVERVIEW', subheader_fmt)
        row += 1
        
        # Headers
        ws.write(row, 1, "Category", table_header_fmt)
        ws.write(row, 2, "GSTR-2B", table_header_fmt)
        ws.write(row, 3, "Books", table_header_fmt)
        ws.write(row, 4, "Notes", table_header_fmt)
        row += 1
        
        # B2B
        ws.write(row, 1, "Regular Invoices (B2B)", label_fmt)
        ws.write(row, 2, b2b_2b, curr_fmt)
        ws.write(row, 3, b2b_books, curr_fmt)
        ws.write(row, 4, "Normal Invoices", workbook.add_format({'border': 1}))
        row += 1
        
        # CDNR
        ws.write(row, 1, "Credit/Debit Notes (CDNR)", label_fmt)
        ws.write(row, 2, cdnr_2b, curr_fmt)
        ws.write(row, 3, cdnr_books, curr_fmt) 
        ws.write(row, 4, "Derived from Type 'CDNR'", workbook.add_format({'border': 1}))
        row += 1
        
        # Net Total
        ws.write(row, 1, "NET TAX TOTAL", label_fmt)
        ws.write(row, 2, total_2b, curr_fmt)
        ws.write(row, 3, total_books, curr_fmt)
        ws.write(row, 4, "", workbook.add_format({'border': 1}))
        row += 1
        
        # Difference
        ws.write(row, 1, "DIFFERENCE (2B - Books)", label_fmt)
        final_diff_fmt = diff_neg_fmt if tax_difference < 0 else diff_pos_fmt
        ws.merge_range(row, 2, row, 3, tax_difference, final_diff_fmt)
        ws.write(row, 4, "Positive = Excess in 2B", workbook.add_format({'border': 1, 'italic': True, 'font_color': '#64748B'}))
        
        # -- Record Statistics --
        row += 3
        ws.merge_range(row, 1, row, 4, 'RECORD STATISTICS', subheader_fmt)
        row += 1
        
        # --- FIX IS HERE: COMMAS ADDED CORRECTLY ---
        stats = [
            ("Matched", len(results_dict["matched"])),
            ("Mismatch", len(results_dict["mismatch_probable"])),
            ("Invoice No Issue", len(results_dict["invoice_mismatch"])),
            ("Only in 2B", len(results_dict["only_2b"])),
            ("Out of Period", len(results_dict["out_of_period"])), 
            ("Only in Books", len(results_dict["only_books"]))
        ]
        
        # Headers for Stats
        ws.write(row, 1, "Category", table_header_fmt)
        ws.merge_range(row, 2, row, 3, "Count", table_header_fmt)
        ws.write(row, 4, "Status", table_header_fmt)
        row += 1
        
        for name, val in stats:
            ws.write(row, 1, name, label_fmt)
            ws.merge_range(row, 2, row, 3, val, count_fmt) 
            
            # Status Logic
            status_text = "Review Required"
            if name == "Matched":
                status_text = "OK"
            elif name == "Out of Period":
                status_text = "Check Dates"
                
            ws.write(row, 4, status_text, workbook.add_format({'border': 1, 'align': 'center'}))
            row += 1

        # --- DATA SHEETS STYLING ---
        sheet_map = {
            "matched": ("Matched Records", '#D1FAE5'),          
            "mismatch_probable": ("Probable Mismatches", '#FED7AA'), 
            "invoice_mismatch": ("Invoice Number Issues", '#FEF08A'),
            "only_2b": ("Missing in Books", '#FECACA'),         
            "only_books": ("Missing in Portal", '#E9D5FF'),     
            "out_of_period": ("Out of Period", '#E2E8F0')       
        }

        data_header_fmt = workbook.add_format({'bold': True, 'font_size': 10, 'font_color': 'white', 'bg_color': '#334155', 'border': 1, 'text_wrap': True, 'align': 'center', 'valign': 'vcenter'})
        row_fmt_even = workbook.add_format({'border': 1, 'bg_color': '#F8FAFC'})
        row_fmt_odd = workbook.add_format({'border': 1, 'bg_color': '#FFFFFF'})
        date_fmt = workbook.add_format({'num_format': 'dd-mm-yyyy', 'border': 1, 'align': 'center'})
        
        for key, (sheet_title, title_color) in sheet_map.items():
            df = results_dict.get(key)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                # Add Sheet
                ws_data = workbook.add_worksheet(sheet_title[:31]) 
                writer.sheets[sheet_title[:31]] = ws_data
                
                # 1. Main Sheet Title
                title_style = workbook.add_format({
                    'bold': True, 'font_size': 14, 'font_color': '#1E293B', 
                    'bg_color': title_color, 'align': 'center', 'valign': 'vcenter', 'border': 1
                })
                ws_data.merge_range(0, 0, 0, len(df.columns)-1, sheet_title.upper(), title_style)
                
                # 2. Column Headers
                for col_num, col_name in enumerate(df.columns):
                    ws_data.write(1, col_num, col_name, data_header_fmt)
                    ws_data.set_column(col_num, col_num, 15 if len(col_name) < 15 else 22)

                # 3. Data Rows
                for r_idx, row_data in df.iterrows():
                    curr_row = r_idx + 2
                    row_style = row_fmt_even if curr_row % 2 == 0 else row_fmt_odd
                    
                    for c_idx, val in enumerate(row_data):
                        # Date Formatting
                        if "Date" in df.columns[c_idx] and pd.notnull(val) and val != "":
                             ws_data.write_datetime(curr_row, c_idx, pd.to_datetime(val), date_fmt)
                        # Numeric Formatting
                        elif isinstance(val, (int, float)) and any(k in df.columns[c_idx] for k in ['Tax', 'IGST', 'CGST', 'SGST', 'Gross', 'Cess']):
                             ws_data.write(curr_row, c_idx, val, workbook.add_format({'num_format': '#,##0.00', 'border': 1}))
                        # Standard Text
                        else:
                             ws_data.write(curr_row, c_idx, str(val), row_style)

    output.seek(0)
    return output
# ---------------------------
# API VIEW
# ---------------------------
class ReconcileView(APIView):
    def post(self, request):
        try:
            file_2b = request.FILES.get("file_2b")
            file_books = request.FILES.get("file_books")

            if not file_2b or not file_books:
                return Response({"detail": "Both files required"}, status=400)

            selected_fy = request.data.get("selected_fy")
            period_type = request.data.get("period_type")
            selected_period_val = request.data.get("selected_period_val")
            tolerance = int(request.data.get("tolerance", 1))

            # ---------------------------
            # 1. PROCESS GSTR-2B
            # ---------------------------
            xls_2b = pd.ExcelFile(file_2b)
            sheets_2b = xls_2b.sheet_names
            
            # A. Read Main Sheet (Sheet 0)
            df_2b_main = pd.read_excel(xls_2b, 0)
            df_2b_main = normalize_columns(df_2b_main)
            df_2b_main = preprocess_data(df_2b_main)
            df_2b_main["Type"] = "B2B"

            # B. Read CDNR Sheet (if exists)
            # Make case-insensitive match looser
            cdnr_sheet_name = next((s for s in sheets_2b if "cdnr" in s.lower() or "credit" in s.lower()), None)
            
            df_2b_cdnr = pd.DataFrame()
            
            if cdnr_sheet_name:
                raw_cdnr = pd.read_excel(xls_2b, cdnr_sheet_name)
                raw_cdnr = normalize_columns(raw_cdnr)
                
                # Loose renaming map
                rename_map = {
                    "Credit/Debit Note No": "Invoice", "Note No": "Invoice", "Note No.": "Invoice",
                    "Credit/Debit Note Date": "Date", "Note Date": "Date", "Note Date.": "Date",
                    "Taxable Value": "Taxable", "Taxable Val": "Taxable",
                    "Integrated Tax": "IGST", "Central Tax": "CGST", "State/UT Tax": "SGST"
                }
                
                actual_rename = {k: v for k, v in rename_map.items() if k in raw_cdnr.columns}
                raw_cdnr = raw_cdnr.rename(columns=actual_rename)
                
                df_2b_cdnr = preprocess_data(raw_cdnr)
                df_2b_cdnr["Type"] = "CDNR"

            # C. Combine 2B
            df_2b_final = pd.concat([df_2b_main, df_2b_cdnr], ignore_index=True)

            # ---------------------------
            # 2. PROCESS BOOKS (Sheet 0 Only)
            # ---------------------------
            # Strictly read sheet 0
            df_books_raw = pd.read_excel(file_books, sheet_name=0)
            df_books_raw = normalize_columns(df_books_raw)
            df_books_final = preprocess_data(df_books_raw)

            # ---------------------------
            # 3. CALCULATE TOTALS (After Preprocessing)
            # ---------------------------
            def get_tax_sum(df):
                if df.empty: return 0.0
                return (df["IGST"].sum() + df["CGST"].sum() + df["SGST"].sum() + df["Cess"].sum())

            # 2B Breakdown
            b2b_2b_sum = get_tax_sum(df_2b_final[df_2b_final["Type"] != "CDNR"])
            cdnr_2b_sum = get_tax_sum(df_2b_final[df_2b_final["Type"] == "CDNR"])

            # Books Breakdown (Based solely on Type column in Sheet 0)
            b2b_books_sum = get_tax_sum(df_books_final[df_books_final["Type"] != "CDNR"])
            cdnr_books_sum = get_tax_sum(df_books_final[df_books_final["Type"] == "CDNR"])

            totals = {
                "b2b_tax_2b": round(b2b_2b_sum, 2),
                "cdnr_tax_2b": round(cdnr_2b_sum, 2),
                "b2b_tax_books": round(b2b_books_sum, 2),
                "cdnr_tax_books": round(cdnr_books_sum, 2)
            }

            # ---------------------------
            # 4. RUN RECONCILIATION
            # ---------------------------
            target_dates, period_label = get_target_periods(selected_fy, period_type, selected_period_val)
            
            results = run_reconciliation(df_2b_final, df_books_final, target_dates, tolerance)
            results["original_totals"] = totals

            # ---------------------------
            # 5. EXPORT / RESPONSE
            # ---------------------------
            if request.query_params.get("export") == "excel":
                excel_file = generate_advanced_excel(results, period_label)
                response = HttpResponse(excel_file.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                response['Content-Disposition'] = f'attachment; filename="Reconciliation_{period_label}.xlsx"'
                return response

            # API Response helper
            def clean_for_json(df):
                if df is None or df.empty: return []
                df = df.fillna("").replace([np.inf, -np.inf], 0)
                # Convert dates to string for JSON
                for col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].dt.strftime("%Y-%m-%d")
                return df.to_dict(orient="records")

            return Response({
                "periodLabel": period_label,
                "tolerance": tolerance,
                "metrics": {k: len(v) if isinstance(v, pd.DataFrame) else 0 for k, v in results.items() if k != "original_totals"},
                "tables": {k: clean_for_json(v) for k, v in results.items() if k != "original_totals" and isinstance(v, pd.DataFrame)}
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({"detail": str(e)}, status=500)