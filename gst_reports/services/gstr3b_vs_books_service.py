# gst_reports/services/gstr3b_vs_books_service.py

import pandas as pd
from datetime import datetime
from gst_reports.services.gst_data_service import GSTDataService

class GSTR3BBooksReconciliationService:
    """
    Service class for GSTR-3B vs Books Reconciliation.
    """
    
    def __init__(self, taxpayer_token=None):
        self.taxpayer_token = taxpayer_token

    @staticmethod
    def get_months_list(reco_type, year, month=None, quarter=None):
        if reco_type == "MONTHLY":
            return [(year, month)]
        if reco_type == "QUARTERLY":
            q_map = {"Q1": [4, 5, 6], "Q2": [7, 8, 9], "Q3": [10, 11, 12], "Q4": [1, 2, 3]}
            return [(year if m >= 4 else year + 1, m) for m in q_map.get(quarter, [])]
        if reco_type == "FY":
            return [(year, m) for m in range(4, 13)] + [(year + 1, m) for m in range(1, 4)]
        return []

    def normalize_books(self, df, months_list):
        """
        Normalize Books Excel data for 3B reconciliation.
        """
        df.columns = df.columns.astype(str).str.strip()
        
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors='coerce')
            mask = df["Date"].apply(lambda x: (x.year, x.month) in months_list if pd.notnull(x) else False)
            df = df[mask].copy()

        if df.empty:
            return pd.DataFrame()
        
        numeric_cols = ["Taxable", "Export_Taxable", "SEZ_Taxable", "Nil_Rated", "Exempt", "Non_GST", "IGST", "CGST", "SGST", "Cess"]
        for col in numeric_cols:
            if col not in df.columns:
                df[col] = 0.0
            else:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                
        df["Is_RCM"] = df.get("Is_RCM", "N").fillna("N").astype(str).str.upper().str.strip()

        rows = []
        for _, r in df.iterrows():
            igst, cgst, sgst = r["IGST"], r["CGST"], r["SGST"]
            tax_amount = igst + cgst + sgst
            
            sup_cat = "DOM"
            taxable_val = 0.0
            
            if r["Is_RCM"] == "Y":
                sup_cat = "RCM"
                taxable_val = r["Taxable"] + r["Export_Taxable"] + r["SEZ_Taxable"] + r["Nil_Rated"] + r["Exempt"] + r["Non_GST"]
            elif r["Export_Taxable"] > 0:
                sup_cat = "EXPWP" if tax_amount > 0 else "EXPWOP"
                taxable_val = r["Export_Taxable"]
            elif r["SEZ_Taxable"] > 0:
                sup_cat = "SEZWP" if tax_amount > 0 else "SEZWOP"
                taxable_val = r["SEZ_Taxable"]
            elif r["Nil_Rated"] > 0 or r["Exempt"] > 0:
                sup_cat = "NIL"
                taxable_val = r["Nil_Rated"] + r["Exempt"]
            elif r["Non_GST"] > 0:
                sup_cat = "NON_GST"
                taxable_val = r["Non_GST"]
            else:
                sup_cat = "DOM"
                taxable_val = r["Taxable"]

            rows.append({
                "SUP_CAT": sup_cat,
                "Taxable": taxable_val,
                "IGST": igst,
                "CGST": cgst,
                "SGST": sgst,
                "Year": r["Date"].year if pd.notnull(r["Date"]) else 0,
                "Month": r["Date"].month if pd.notnull(r["Date"]) else 0
            })

        return pd.DataFrame(rows)

    def calculate_books_summary(self, norm_df, months_list):
        sections = ["3.1(a)", "3.1(b)", "3.1(c)", "3.1(d)", "3.1(e)"]
        def init_metrics(): return {"taxable": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "tax": 0.0}

        monthly_data = {}
        for y, m in months_list:
            m_key = f"{y}-{m:02d}"
            monthly_data[m_key] = {k: init_metrics() for k in sections}

        if norm_df.empty:
            return monthly_data

        for _, r in norm_df.iterrows():
            if r["Year"] == 0 or r["Month"] == 0: continue
            m_key = f"{int(r['Year'])}-{int(r['Month']):02d}"
            if m_key not in monthly_data: continue

            key = None
            if r["SUP_CAT"] == "RCM": key = "3.1(d)"
            elif r["SUP_CAT"] in ("EXPWP", "EXPWOP", "SEZWP", "SEZWOP"): key = "3.1(b)"
            elif r["SUP_CAT"] == "NIL": key = "3.1(c)"
            elif r["SUP_CAT"] == "NON_GST": key = "3.1(e)"
            elif r["SUP_CAT"] == "DOM": key = "3.1(a)"
                
            if key:
                monthly_data[m_key][key]["taxable"] += r["Taxable"]
                monthly_data[m_key][key]["igst"] += r["IGST"]
                monthly_data[m_key][key]["cgst"] += r["CGST"]
                monthly_data[m_key][key]["sgst"] += r["SGST"]
                monthly_data[m_key][key]["tax"] += (r["IGST"] + r["CGST"] + r["SGST"])
        
        return monthly_data

    def fetch_portal_summary(self, months_list, gstin, force_refresh=False):
        sections = ["3.1(a)", "3.1(b)", "3.1(c)", "3.1(d)", "3.1(e)"]
        def init_metrics(): return {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0, "tax": 0}

        monthly_data = {}
        for y, m in months_list:
            m_key = f"{y}-{m:02d}"
            monthly_data[m_key] = {k: init_metrics() for k in sections}
            
            response_data = GSTDataService.get_gstr3b_filed(
                gstin=gstin, year=y, month=m, taxpayer_token=self.taxpayer_token, force_refresh=force_refresh
            )
            if not response_data: continue
            
            sup = response_data.get("sup_details", {})
            
            def process_sec(sec_key, source_dict):
                if not source_dict: return
                txval, iamt, camt, samt = source_dict.get("txval", 0), source_dict.get("iamt", 0), source_dict.get("camt", 0), source_dict.get("samt", 0)
                monthly_data[m_key][sec_key]["taxable"] += txval
                monthly_data[m_key][sec_key]["igst"] += iamt
                monthly_data[m_key][sec_key]["cgst"] += camt
                monthly_data[m_key][sec_key]["sgst"] += samt
                monthly_data[m_key][sec_key]["tax"] += (iamt + camt + samt)

            process_sec("3.1(a)", sup.get("osup_det"))
            process_sec("3.1(b)", sup.get("osup_zero"))
            process_sec("3.1(c)", sup.get("osup_nil_exmp")) 
            process_sec("3.1(d)", sup.get("isup_rev"))
            process_sec("3.1(e)", sup.get("osup_nongst"))

        return monthly_data

    def run(self, df, reco_type, year, gstin, month=None, quarter=None, force_refresh=False):
        months_list = self.get_months_list(reco_type, year, month, quarter)
        norm_df = self.normalize_books(df, months_list)
        books_summary = self.calculate_books_summary(norm_df, months_list)
        portal_summary = self.fetch_portal_summary(months_list, gstin, force_refresh)

        particular_mapping = [
            ("3.1.a Taxable Value", "3.1(a)", "taxable"),
            ("3.1.a IGST", "3.1(a)", "igst"),
            ("3.1.a CGST", "3.1(a)", "cgst"),
            ("3.1.a SGST", "3.1(a)", "sgst"),
            ("3.1.b Exports Taxable", "3.1(b)", "taxable"),
            ("3.1.b Exports IGST", "3.1(b)", "igst"),
            ("3.1.c Nil/Exempt", "3.1(c)", "taxable"),
            ("3.1.e Non-GST", "3.1(e)", "taxable"),
        ]

        final_report = []
        for m in sorted(books_summary.keys()):
            rows = []
            status = "MATCHED"
            for label, sec, field in particular_mapping:
                v1 = books_summary[m].get(sec, {}).get(field, 0)
                v2 = portal_summary.get(m, {}).get(sec, {}).get(field, 0)
                diff = v1 - v2
                if abs(diff) > 1.0: status = "MISMATCHED"
                rows.append({"particular": label, "v1": v1, "v2": v2, "diff": diff})
            
            final_report.append({
                "month": datetime.strptime(m, "%Y-%m").strftime("%b %Y"),
                "month_key": m,
                "status": status,
                "rows": rows
            })
            
        return final_report
