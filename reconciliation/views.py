from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse

import pandas as pd
import numpy as np
from datetime import datetime
import io

# ---------------------------
# CONSTANTS
# ---------------------------
REQUIRED_COLUMNS = [
    "GSTIN/UIN", "Supplier", "Invoice", "Date",
    "Gross Amt", "Taxable", "IGST", "SGST", "CGST", "Type"
]

NUMERIC_COLUMNS = ["Gross Amt", "Taxable", "IGST", "SGST", "CGST"]


# ---------------------------
# HELPER FUNCTIONS
# ---------------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    return df


def validate_structure(df: pd.DataFrame, filename: str):
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        return False, f"Error in {filename}: Missing columns: {', '.join(missing)}"
    return True, ""


def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Clean Invoice
    if "Invoice" in df.columns:
        df["Invoice"] = (
            df["Invoice"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .replace("nan", "")
        )
        df["Invoice_Clean"] = df["Invoice"].str.strip().str.upper()

    # Clean GSTIN
    if "GSTIN/UIN" in df.columns:
        df["GSTIN/UIN"] = df["GSTIN/UIN"].astype(str).replace("nan", "")
        df["GSTIN_Clean"] = df["GSTIN/UIN"].str.strip().str.upper()

    # Date parsing
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")

    return df


def get_target_periods(fy_string: str, period_type: str, selected_period: str):
    """Return list of (month, year) tuples and label."""
    start_year = int(fy_string.split("-")[0])
    end_year = int(fy_string.split("-")[1])

    target_dates = []
    period_label = ""

    if period_type == "Monthly":
        month_map = {
            "April": 4, "May": 5, "June": 6, "July": 7, "August": 8, "September": 9,
            "October": 10, "November": 11, "December": 12, "January": 1, "February": 2, "March": 3
        }
        m_num = month_map[selected_period]
        y_num = start_year if m_num >= 4 else end_year
        target_dates = [(m_num, y_num)]
        period_label = f"{selected_period} {y_num}"
    else:
        if selected_period == "Q1 (Apr-Jun)":
            target_dates = [(4, start_year), (5, start_year), (6, start_year)]
        elif selected_period == "Q2 (Jul-Sep)":
            target_dates = [(7, start_year), (8, start_year), (9, start_year)]
        elif selected_period == "Q3 (Oct-Dec)":
            target_dates = [(10, start_year), (11, start_year), (12, start_year)]
        elif selected_period == "Q4 (Jan-Mar)":
            target_dates = [(1, end_year), (2, end_year), (3, end_year)]
        period_label = f"{selected_period} ({fy_string})"

    return target_dates, period_label


def values_match_within_tolerance(val1, val2, tolerance):
    return abs(val1 - val2) <= tolerance


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

    # Filter
    df_books_current = df_books[is_in_period(df_books)].copy()
    df_2b_current = df_2b[is_in_period(df_2b)].copy()

    df_books_out = df_books[~is_in_period(df_books)].copy()
    df_books_out["Source"] = "Books"

    df_2b_out = df_2b[~is_in_period(df_2b)].copy()
    df_2b_out["Source"] = "GSTR-2B"

    df_out_of_period = pd.concat([df_books_out, df_2b_out], ignore_index=True)

    # -----------------------------------------------------
    # LOGIC:
    # 1. Matched: Exact GSTIN, Invoice, & All Values
    # 2. Invoice Mismatch: GSTIN Match, Values Match, Invoice Different
    # 3. Mismatch/Probable: GSTIN Match, but Values Diff OR Invoice Diff (and values diff)
    # 4. Orphans (Only in 2B / Only in Books)
    # -----------------------------------------------------

    # --- STEP 1: Exact Key Match (GSTIN + Invoice) ---
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
    results_mismatch_probable = []  # Value mismatch or fuzzy mismatch
    results_invoice_mismatch = []
    results_only_2b = []
    results_only_books = []

    # Process Exact Key Matches (Check Values)
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
            "Invoice_2B": safe_str(
                row.get("Invoice_Original_2B_2b")
                if "Invoice_Original_2B_2b" in row
                else row.get("Invoice_2b")
            ),
            "Invoice_Books": safe_str(
                row.get("Invoice_Original_Books_books")
                if "Invoice_Original_Books_books" in row
                else row.get("Invoice_books")
            ),
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
            "Gross_2B": row.get("Gross Amt_2b", 0),
            "Gross_Books": row.get("Gross Amt_books", 0),
            "Gross_Diff": round(abs(row.get("Gross Amt_2b", 0) - row.get("Gross Amt_books", 0)), 2)
        }

        if is_val_match:
            results_matched.append(base_data)
        else:
            # Key matched, but values differ -> mismatch/probable
            results_mismatch_probable.append(base_data)

    # --- STEP 2: Fuzzy Match on Leftovers (GSTIN Only) ---
    cols_2b = {col: col.replace("_2b", "") for col in leftover_2b.columns if "_2b" in col}
    cols_2b.update({"GSTIN_Clean": "GSTIN_Clean", "Invoice_Clean": "Invoice_Original_2B"})
    unique_cols_2b = list(dict.fromkeys(list(cols_2b.keys()) + ["GSTIN_Clean"]))
    df_2b_candidate = leftover_2b[unique_cols_2b].rename(columns=cols_2b)

    cols_books = {
        col: col.replace("_books", "") for col in leftover_books.columns if "_books" in col
    }
    cols_books.update({"GSTIN_Clean": "GSTIN_Clean", "Invoice_Clean": "Invoice_Original_Books"})
    unique_cols_books = list(dict.fromkeys(list(cols_books.keys()) + ["GSTIN_Clean"]))
    df_books_candidate = leftover_books[unique_cols_books].rename(columns=cols_books)

    unmatched_2b_indices = set(df_2b_candidate.index)
    unmatched_books_indices = set(df_books_candidate.index)

    # Nested loop fuzzy match within same GSTIN
    for idx_2b, row_2b in df_2b_candidate.iterrows():
        possible_books = df_books_candidate[df_books_candidate["GSTIN_Clean"] == row_2b["GSTIN_Clean"]]
        match_found = False

        for idx_books, row_books in possible_books.iterrows():
            if idx_books not in unmatched_books_indices:
                continue

            if (
                values_match_within_tolerance(row_2b.get("Taxable", 0), row_books.get("Taxable", 0), tolerance)
                and values_match_within_tolerance(row_2b.get("IGST", 0), row_books.get("IGST", 0), tolerance)
                and values_match_within_tolerance(row_2b.get("CGST", 0), row_books.get("CGST", 0), tolerance)
                and values_match_within_tolerance(row_2b.get("SGST", 0), row_books.get("SGST", 0), tolerance)
            ):
                gross_match = values_match_within_tolerance(
                    row_2b.get("Gross Amt", 0), row_books.get("Gross Amt", 0), tolerance
                )

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
                    "Gross_2B": row_2b.get("Gross Amt", 0),
                    "Gross_Books": row_books.get("Gross Amt", 0),
                    "Gross_Diff": round(abs(row_2b.get("Gross Amt", 0) - row_books.get("Gross Amt", 0)), 2)
                }

                if gross_match:
                    results_invoice_mismatch.append(base_data)
                else:
                    results_mismatch_probable.append(base_data)

                unmatched_2b_indices.discard(idx_2b)
                unmatched_books_indices.discard(idx_books)
                match_found = True
                break

        # If no match_found → remains orphan (handled later)

    # --- STEP 3: Orphans ---

    # Only in 2B
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
            "Gross_2B": row.get("Gross Amt", 0),
            "Gross_Books": 0,
            "Gross_Diff": 0
        })

    # Only in Books
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
            "Gross_2B": 0,
            "Gross_Books": row.get("Gross Amt", 0),
            "Gross_Diff": 0
        })

    # Convert to DataFrames
    df_matched = pd.DataFrame(results_matched)
    df_mismatch_probable = pd.DataFrame(results_mismatch_probable)
    df_invoice_mismatch = pd.DataFrame(results_invoice_mismatch)
    df_only_2b = pd.DataFrame(results_only_2b)
    df_only_books = pd.DataFrame(results_only_books)

    # Helper for Date Sorting/Formatting
    def format_df(df):
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return df
        if "Date_2B" in df.columns:
            df["Date_2B"] = pd.to_datetime(df["Date_2B"], errors="coerce")
            df = df.sort_values(by="Date_2B")
        elif "Date_Books" in df.columns:
            df["Date_Books"] = pd.to_datetime(df["Date_Books"], errors="coerce")
            df = df.sort_values(by="Date_Books")
        return df

    df_matched = format_df(df_matched)
    df_mismatch_probable = format_df(df_mismatch_probable)
    df_invoice_mismatch = format_df(df_invoice_mismatch)
    df_only_2b = format_df(df_only_2b)
    df_only_books = format_df(df_only_books)
    df_out_of_period = format_df(df_out_of_period)

    # Robust Cleanup
    def clean_nans(df):
        if df is None:
            return df
        if not isinstance(df, pd.DataFrame):
            try:
                df = pd.DataFrame(df)
            except Exception:
                return df

        # Replace Inf with 0
        df = df.replace([np.inf, -np.inf], 0)
        # Fill numeric NaNs with 0
        num_cols = df.select_dtypes(include=['number']).columns
        df[num_cols] = df[num_cols].fillna(0)
        # Fill remaining NaNs with empty string
        df = df.fillna("")
        return df

    # Apply cleanup to all dataframes
    df_matched = clean_nans(df_matched)
    df_mismatch_probable = clean_nans(df_mismatch_probable)
    df_invoice_mismatch = clean_nans(df_invoice_mismatch)
    df_only_2b = clean_nans(df_only_2b)
    df_only_books = clean_nans(df_only_books)
    df_out_of_period = clean_nans(df_out_of_period)

    # Return dictionary of DataFrames for easier access
    return {
        "matched": df_matched,
        "mismatch_probable": df_mismatch_probable,
        "invoice_mismatch": df_invoice_mismatch,
        "only_2b": df_only_2b,
        "only_books": df_only_books,
        "out_of_period": df_out_of_period
    }


def generate_advanced_excel(results_dict, period_label):
    """
    Generate a professional Excel report with colors, headers, and formatting.
    Replace the existing generate_advanced_excel function with this one.
    """
    output = io.BytesIO()

    # Calculate Summary
    total_2b = 0
    total_books = 0

    for key, df in results_dict.items():
        if key == "out_of_period":
            continue
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            continue
        
        if "IGST_2B" in df.columns: total_2b += df["IGST_2B"].sum()
        if "CGST_2B" in df.columns: total_2b += df["CGST_2B"].sum()
        if "SGST_2B" in df.columns: total_2b += df["SGST_2B"].sum()
        
        if "IGST_Books" in df.columns: total_books += df["IGST_Books"].sum()
        if "CGST_Books" in df.columns: total_books += df["CGST_Books"].sum()
        if "SGST_Books" in df.columns: total_books += df["SGST_Books"].sum()

    tax_difference = round(total_2b - total_books, 2)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        
        # ==========================================
        # DEFINE COLOR FORMATS
        # ==========================================
        
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'font_color': '#FFFFFF',
            'bg_color': '#2563EB',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        subheader_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'font_color': '#1E293B',
            'bg_color': '#E0F2FE',
            'align': 'left',
            'valign': 'vcenter',
            'border': 1
        })
        
        currency_format = workbook.add_format({
            'num_format': '₹#,##0.00',
            'bold': True,
            'font_size': 12,
            'align': 'right',
            'border': 1
        })
        
        currency_positive = workbook.add_format({
            'num_format': '₹#,##0.00',
            'bold': True,
            'font_size': 12,
            'font_color': '#16A34A',
            'align': 'right',
            'border': 1
        })
        
        currency_negative = workbook.add_format({
            'num_format': '₹#,##0.00',
            'bold': True,
            'font_size': 12,
            'font_color': '#DC2626',
            'align': 'right',
            'border': 1
        })
        
        table_header_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'font_color': '#FFFFFF',
            'bg_color': '#475569',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'text_wrap': True
        })
        
        table_cell_format = workbook.add_format({
            'font_size': 10,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1
        })
        
        number_format = workbook.add_format({
            'font_size': 10,
            'num_format': '#,##0',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Status Colors
        matched_format = workbook.add_format({
            'bold': True,
            'font_color': '#FFFFFF',
            'bg_color': '#16A34A',
            'align': 'center',
            'border': 1
        })
        
        warning_format = workbook.add_format({
            'bold': True,
            'font_color': '#FFFFFF',
            'bg_color': '#EA580C',
            'align': 'center',
            'border': 1
        })
        
        error_format = workbook.add_format({
            'bold': True,
            'font_color': '#FFFFFF',
            'bg_color': '#DC2626',
            'align': 'center',
            'border': 1
        })
        
        # ==========================================
        # EXECUTIVE SUMMARY SHEET
        # ==========================================
        
        ws = workbook.add_worksheet("Executive Summary")
        writer.sheets["Executive Summary"] = ws
        
        # Set column widths
        ws.set_column('A:A', 5)
        ws.set_column('B:B', 30)
        ws.set_column('C:C', 20)
        ws.set_column('D:D', 40)
        
        # Merge cells for title
        ws.merge_range('B2:D2', f'GST RECONCILIATION REPORT - {period_label}', header_format)
        
        # Financial Summary Section
        ws.merge_range('B4:D4', 'FINANCIAL SUMMARY', subheader_format)
        
        ws.write('B6', 'Total Tax (GSTR-2B)', table_header_format)
        ws.write('C6', total_2b, currency_positive)
        
        ws.write('B7', 'Total Tax (Books)', table_header_format)
        ws.write('C7', total_books, currency_positive)
        
        ws.write('B8', 'Tax Difference', table_header_format)
        diff_format = currency_negative if tax_difference < 0 else currency_positive
        ws.write('C8', tax_difference, diff_format)
        
        # Reconciliation Summary Section
        ws.merge_range('B10:D10', 'RECONCILIATION SUMMARY', subheader_format)
        
        summary_data = [
            ("Matched", len(results_dict["matched"]), "No Action Required", matched_format),
            ("Mismatch / Probable", len(results_dict["mismatch_probable"]), "Verify Values & GSTIN", warning_format),
            ("Invoice Mismatch", len(results_dict["invoice_mismatch"]), "Correct Invoice Numbers", warning_format),
            ("Only in GSTR-2B", len(results_dict["only_2b"]), "Record Missing Invoices", error_format),
            ("Only in Books", len(results_dict["only_books"]), "Follow Up with Supplier", error_format),
        ]
        
        ws.write('B12', 'Category', table_header_format)
        ws.write('C12', 'Count', table_header_format)
        ws.write('D12', 'Recommended Action', table_header_format)
        
        row_idx = 13
        for category, count, action, fmt in summary_data:
            ws.write(row_idx, 1, category, fmt)
            ws.write(row_idx, 2, count, number_format)
            ws.write(row_idx, 3, action, table_cell_format)
            row_idx += 1
        
        # Add timestamp
        timestamp_format = workbook.add_format({
            'italic': True,
            'font_size': 9,
            'font_color': '#64748B',
            'align': 'right'
        })
        ws.merge_range(f'B{row_idx + 2}:D{row_idx + 2}', 
                       f'Report Generated: {datetime.now().strftime("%d-%b-%Y %I:%M %p")}', 
                       timestamp_format)

        # ==========================================
        # DATA SHEETS WITH FORMATTING
        # ==========================================
        
        sheet_map = {
            "matched": ("Matched", '#D1FAE5'),
            "mismatch_probable": ("Mismatch-Probable", '#FED7AA'),
            "invoice_mismatch": ("Invoice Mismatch", '#FEF08A'),
            "only_2b": ("Only in GSTR-2B", '#FECACA'),
            "only_books": ("Only in Books", '#E9D5FF'),
            "out_of_period": ("Out of Period", '#E2E8F0')
        }

        for key, (name, bg_color) in sheet_map.items():
            df = results_dict.get(key)
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                df.to_excel(writer, index=False, sheet_name=name, startrow=1)
                ws_data = writer.sheets[name]
                
                # Format header row
                header_bg_format = workbook.add_format({
                    'bold': True,
                    'font_size': 11,
                    'font_color': '#FFFFFF',
                    'bg_color': '#1E293B',
                    'align': 'center',
                    'valign': 'vcenter',
                    'border': 1,
                    'text_wrap': True
                })
                
                # Write sheet title
                title_format = workbook.add_format({
                    'bold': True,
                    'font_size': 14,
                    'font_color': '#1E293B',
                    'bg_color': bg_color,
                    'align': 'center',
                    'valign': 'vcenter',
                    'border': 1
                })
                ws_data.merge_range(0, 0, 0, len(df.columns)-1, name.upper(), title_format)
                
                # Format headers
                for col_num, col_name in enumerate(df.columns):
                    ws_data.write(1, col_num, col_name, header_bg_format)
                    ws_data.set_column(col_num, col_num, 18)
                
                # Format data with currency for amount columns
                currency_cell_format = workbook.add_format({
                    'num_format': '₹#,##0.00',
                    'border': 1
                })
                
                date_cell_format = workbook.add_format({
                    'num_format': 'dd-mmm-yyyy',
                    'border': 1
                })
                
                # Alternate row colors
                for row_num in range(len(df)):
                    row_format = workbook.add_format({
                        'bg_color': '#F8FAFC' if row_num % 2 == 0 else '#FFFFFF',
                        'border': 1
                    })
                    
                    for col_num in range(len(df.columns)):
                        col_name = df.columns[col_num]
                        cell_value = df.iloc[row_num, col_num]
                        
                        # Handle NaT (Not a Time) and NaN values
                        if pd.isna(cell_value):
                            cell_value = ""
                        
                        # Apply currency format to amount columns
                        if any(keyword in col_name for keyword in ['Taxable', 'IGST', 'CGST', 'SGST', 'Gross']):
                            format_to_use = workbook.add_format({
                                'num_format': '₹#,##0.00',
                                'bg_color': '#F8FAFC' if row_num % 2 == 0 else '#FFFFFF',
                                'border': 1
                            })
                            ws_data.write(row_num + 2, col_num, cell_value, format_to_use)
                        elif 'Date' in col_name:
                            format_to_use = workbook.add_format({
                                'bg_color': '#F8FAFC' if row_num % 2 == 0 else '#FFFFFF',
                                'border': 1
                            })
                            # Only write as date if it's actually a valid datetime
                            if isinstance(cell_value, (pd.Timestamp, datetime)):
                                ws_data.write_datetime(row_num + 2, col_num, cell_value, format_to_use)
                            else:
                                ws_data.write(row_num + 2, col_num, str(cell_value), format_to_use)
                        else:
                            ws_data.write(row_num + 2, col_num, cell_value, row_format)

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
                return Response(
                    {"detail": "Both GSTR-2B and Books files are required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            selected_fy = request.data.get("selected_fy")
            period_type = request.data.get("period_type")
            selected_period_val = request.data.get("selected_period_val")
            tolerance = int(request.data.get("tolerance", 1))

            if not all([selected_fy, period_type, selected_period_val]):
                return Response(
                    {"detail": "selected_fy, period_type and selected_period_val are required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            df_2b = pd.read_excel(file_2b)
            df_books = pd.read_excel(file_books)
            
            # --- GET TOTAL RECORDS ---
            total_records_2b = len(df_2b)
            total_records_books = len(df_books)

            df_2b = normalize_columns(df_2b)
            df_books = normalize_columns(df_books)

            ok_2b, msg_2b = validate_structure(df_2b, "GSTR-2B")
            ok_books, msg_books = validate_structure(df_books, "Books")
            if not ok_2b or not ok_books:
                return Response(
                    {"detail": ", ".join(filter(None, [msg_2b, msg_books]))},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            df_2b_clean = preprocess_data(df_2b.copy())
            df_books_clean = preprocess_data(df_books.copy())

            target_dates, period_label = get_target_periods(
                selected_fy, period_type, selected_period_val
            )

            # --- RUN RECONCILIATION LOGIC ---
            results_dict = run_reconciliation(
                df_2b_clean, df_books_clean, target_dates, tolerance
            )

            export = request.query_params.get("export")

            if export == "excel":
                excel_buffer = generate_advanced_excel(
                    results_dict, period_label
                )
                resp = HttpResponse(
                    excel_buffer.getvalue(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                filename = f"Reconciliation_Report_{period_label.replace(' ', '_')}.xlsx"
                resp["Content-Disposition"] = f'attachment; filename="{filename}"'
                return resp

            # JSON response for React frontend
            def df_to_records(df):
                if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                    return []

                df = df.copy()

                # Replace Infinite values with 0
                df = df.replace([np.inf, -np.inf], 0)

                # Numeric NaNs → 0
                num_cols = df.select_dtypes(include=["number"]).columns
                df[num_cols] = df[num_cols].fillna(0)

                # Format datetime columns safely
                for col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].dt.strftime("%Y-%m-%d")

                # Remaining NaNs → ""
                df = df.fillna("")

                # Final safety for Inf / NaN
                df = df.replace([np.inf, -np.inf], 0).fillna("")

                return df.to_dict(orient="records")

            data = {
                "periodLabel": period_label,
                "tolerance": tolerance,
                "meta": {
                    "total_records_2b": total_records_2b,
                    "total_records_books": total_records_books
                },
                "metrics": {
                    "matched": len(results_dict["matched"]) if isinstance(results_dict["matched"], pd.DataFrame) else 0,
                    "mismatch_probable": len(results_dict["mismatch_probable"]) if isinstance(results_dict["mismatch_probable"], pd.DataFrame) else 0,
                    "invoice_mismatch": len(results_dict["invoice_mismatch"]) if isinstance(results_dict["invoice_mismatch"], pd.DataFrame) else 0,
                    "only_2b": len(results_dict["only_2b"]) if isinstance(results_dict["only_2b"], pd.DataFrame) else 0,
                    "only_books": len(results_dict["only_books"]) if isinstance(results_dict["only_books"], pd.DataFrame) else 0,
                    "out_period": len(results_dict["out_of_period"]) if isinstance(results_dict["out_of_period"], pd.DataFrame) else 0,
                },
            }

            data["tables"] = {
                "matched": df_to_records(results_dict["matched"]),
                "mismatch_probable": df_to_records(results_dict["mismatch_probable"]),
                "invoice_mismatch": df_to_records(results_dict["invoice_mismatch"]),
                "only_2b": df_to_records(results_dict["only_2b"]),
                "only_books": df_to_records(results_dict["only_books"]),
                "out_of_period": df_to_records(results_dict["out_of_period"]),
            }

            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {"detail": f"Server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
