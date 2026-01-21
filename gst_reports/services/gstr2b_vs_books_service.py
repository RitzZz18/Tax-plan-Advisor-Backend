# gst_reports/services/gstr2b_vs_books_service.py

import pandas as pd
from datetime import datetime
from gst_reports.services.gst_data_service import GSTDataService
from gst_reports.services.gstr2b_excel_service import GSTR2BExcelService

class GSTR2BBooksReconciliationService:
    """
    Service class for GSTR-2B vs Books Reconciliation.
    """
    
    def __init__(self, taxpayer_token=None):
        self.taxpayer_token = taxpayer_token

    def get_months_list(self, reco_type, year, month_name=None, quarter_name=None):
        month_map = {
            "April": 4, "May": 5, "June": 6, "July": 7, "August": 8, "September": 9,
            "October": 10, "November": 11, "December": 12, "January": 1, "February": 2, "March": 3
        }
        
        if reco_type == "Monthly":
            m = month_map.get(month_name)
            return [(year if m >= 4 else year + 1, m)]
        
        if reco_type == "Quarterly":
            q_map = {
                "Q1 (Apr-Jun)": [4, 5, 6],
                "Q2 (Jul-Sep)": [7, 8, 9],
                "Q3 (Oct-Dec)": [10, 11, 12],
                "Q4 (Jan-Mar)": [1, 2, 3]
            }
            months = q_map.get(quarter_name, [])
            return [(year if m >= 4 else year + 1, m) for m in months]
            
        if reco_type == "Yearly":
            return [(year, m) for m in range(4, 13)] + [(year + 1, m) for m in range(1, 4)]
            
        return []

    def fetch_portal_data(self, months_list, gstin, force_refresh=False):
        all_b2b = []
        all_cdnr = []
        
        for y, m in months_list:
            period_str = f"{m:02d}{y}"
            json_data = GSTDataService.get_gstr2b(
                gstin=gstin, 
                year=y, 
                month=m, 
                taxpayer_token=self.taxpayer_token, 
                force_refresh=force_refresh
            )
            if json_data:
                b2b, cdnr = GSTR2BExcelService.extract_data(json_data, period_str)
                all_b2b.extend(b2b)
                all_cdnr.extend(cdnr)
        
        portal_df = pd.DataFrame(all_b2b + all_cdnr)
        if not portal_df.empty:
            # Standardize columns to match reconciliation logic
            portal_df = portal_df.rename(columns={
                "GSTIN/UIN": "GSTIN",
                "Invoice": "Invoice_No",
                "Taxable": "Taxable_Value",
                "IGST": "IGST_Portal",
                "CGST": "CGST_Portal",
                "SGST": "SGST_Portal",
                "Date": "Invoice_Date"
            })
        return portal_df

    def reconcile(self, books_df, portal_df, tolerance=1.0):
        if books_df.empty and portal_df.empty:
            return self.empty_result()
            
        # Basic cleanup
        for df in [books_df, portal_df]:
            if df.empty: continue
            df["GSTIN"] = df["GSTIN"].astype(str).str.upper().str.strip()
            df["Invoice_No"] = df["Invoice_No"].astype(str).str.upper().str.strip()
            if "Taxable_Value" in df.columns:
                df["Taxable_Value"] = pd.to_numeric(df["Taxable_Value"], errors='coerce').fillna(0)
            if "IGST" in df.columns:
                df["IGST"] = pd.to_numeric(df["IGST"], errors='coerce').fillna(0)
        
        # Merge logic
        merged = pd.merge(
            books_df, portal_df, 
            on=["GSTIN", "Invoice_No"], 
            how="outer", 
            suffixes=("_Books", "_Portal")
        )
        
        matched = []
        mismatch = []
        only_books = []
        only_portal = []
        
        for _, row in merged.iterrows():
            in_books = not pd.isna(row.get("Taxable_Value_Books"))
            in_portal = not pd.isna(row.get("Taxable_Value_Portal"))
            
            item = row.to_dict()
            
            if in_books and in_portal:
                diff = abs(row["Taxable_Value_Books"] - row["Taxable_Value_Portal"])
                if diff <= tolerance:
                    matched.append(item)
                else:
                    mismatch.append(item)
            elif in_books:
                only_books.append(item)
            else:
                only_portal.append(item)
                
        return {
            "metrics": {
                "matched": len(matched),
                "mismatch_probable": len(mismatch),
                "invoice_mismatch": 0,
                "only_2b": len(only_portal),
                "only_books": len(only_books),
                "out_period": 0
            },
            "tables": {
                "matched": matched,
                "mismatch_probable": mismatch,
                "invoice_mismatch": [],
                "only_2b": only_portal,
                "only_books": only_books,
                "out_of_period": []
            }
        }

    def empty_result(self):
        return {
            "metrics": {"matched": 0, "mismatch_probable": 0, "invoice_mismatch": 0, "only_2b": 0, "only_books": 0, "out_period": 0},
            "tables": {"matched": [], "mismatch_probable": [], "invoice_mismatch": [], "only_2b": [], "only_books": [], "out_of_period": []}
        }

    def run(self, books_df, reco_type, year, gstin, month_name=None, quarter_name=None, tolerance=1.0, force_refresh=False):
        months_list = self.get_months_list(reco_type, year, month_name, quarter_name)
        portal_df = self.fetch_portal_data(months_list, gstin, force_refresh)
        
        # Clean Books DF
        books_df = books_df.rename(columns={
            "GSTIN/UIN": "GSTIN",
            "Invoice": "Invoice_No",
            "Taxable": "Taxable_Value",
            "Date": "Invoice_Date"
        })
        
        result = self.reconcile(books_df, portal_df, tolerance)
        result["periodLabel"] = f"{reco_type} - {month_name or quarter_name or year}"
        result["tolerance"] = tolerance
        return result
