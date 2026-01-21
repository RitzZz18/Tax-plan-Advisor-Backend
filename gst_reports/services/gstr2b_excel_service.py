import pandas as pd
import io
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from gst_reports.services.gst_data_service import GSTDataService

logger = logging.getLogger(__name__)

class GSTR2BExcelService:
    @staticmethod
    def safe_float(value, default=0.0):
        # ... (same as before)
        if value is None or value == "" or value == "null":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_periods(download_type, fy=None, quarter=None, year=None, month=None):
        if download_type == "fy":
            y = int(fy.split("-")[0])
            now = datetime.now()
            periods = []
            for m in range(4, 13):
                if y < now.year or (y == now.year and m <= now.month): periods.append((y, m))
            for m in range(1, 4):
                if y + 1 < now.year or (y + 1 == now.year and m <= now.month): periods.append((y + 1, m))
            return periods, fy
        elif download_type == "quarterly":
            y = int(fy.split("-")[0])
            q = int(quarter.replace("Q", "")) if isinstance(quarter, str) else quarter
            periods = [(y, 4), (y, 5), (y, 6)] if q == 1 else \
                      [(y, 7), (y, 8), (y, 9)] if q == 2 else \
                      [(y, 10), (y, 11), (y, 12)] if q == 3 else \
                      [(y + 1, 1), (y + 1, 2), (y + 1, 3)]
            return periods, f"{fy}_Q{q}"
        else:
            return [(int(year), int(month))], f"{month}{year}"

    @staticmethod
    def extract_data(json_data, period_str=""):
        b2b_rows = []
        cdnr_rows = []
        
        try:
            from gst_reports.utils import unwrap_sandbox_data
            actual_data = unwrap_sandbox_data(json_data)
            docdata = actual_data.get("docdata")
            if not docdata: return [], []
        except:
            return [], []

        # Process B2B & B2BA
        for key in ["b2b", "b2ba"]:
            data = docdata.get(key, [])
            if isinstance(data, dict): data = list(data.values())
            for supplier in data:
                ctin, trdnm = supplier.get("ctin", ""), supplier.get("trdnm", "")
                invoices = supplier.get("inv", [])
                if isinstance(invoices, dict): invoices = list(invoices.values())
                for inv in invoices:
                    b2b_rows.append({
                        "Return Period": period_str,
                        "GSTIN/UIN": ctin, "Supplier": trdnm, "Invoice": inv.get("inum", ""),
                        "Date": inv.get("dt", ""), "Gross Amt": GSTR2BExcelService.safe_float(inv.get("val")),
                        "Taxable": round(GSTR2BExcelService.safe_float(inv.get("txval")), 2),
                        "IGST": round(GSTR2BExcelService.safe_float(inv.get("igst") or inv.get("iamt")), 2),
                        "CGST": round(GSTR2BExcelService.safe_float(inv.get("cgst") or inv.get("camt")), 2),
                        "SGST": round(GSTR2BExcelService.safe_float(inv.get("samt") or inv.get("sgst")), 2),
                        "Cess": round(GSTR2BExcelService.safe_float(inv.get("cess") or inv.get("csamt")), 2), "Type": key.upper()
                    })

        # Process CDNR & CDNRA
        for key in ["cdnr", "cdnra"]:
            data = docdata.get(key, [])
            if isinstance(data, dict): data = list(data.values())
            for supplier in data:
                ctin, trdnm = supplier.get("ctin", ""), supplier.get("trdnm", "")
                notes = supplier.get("nt", [])
                if isinstance(notes, dict): notes = list(notes.values())
                for note in notes:
                    cdnr_rows.append({
                        "Return Period": period_str,
                        "GSTIN/UIN": ctin, "Supplier": trdnm, 
                        "Invoice": note.get("ntnum", "") or note.get("nt_num", ""),
                        "Date": note.get("dt", ""), "Gross Amt": GSTR2BExcelService.safe_float(note.get("val")),
                        "Taxable": round(GSTR2BExcelService.safe_float(note.get("txval")), 2),
                        "IGST": round(GSTR2BExcelService.safe_float(note.get("iamt") or note.get("igst")), 2),
                        "CGST": round(GSTR2BExcelService.safe_float(note.get("camt") or note.get("cgst")), 2),
                        "SGST": round(GSTR2BExcelService.safe_float(note.get("samt") or note.get("sgst")), 2),
                        "Cess": round(GSTR2BExcelService.safe_float(note.get("cess") or note.get("csamt")), 2), "Type": key.upper()
                    })
        
        return b2b_rows, cdnr_rows

    def generate(self, gstin, taxpayer_token, download_type="monthly", fy=None, quarter=None, year=None, month=None, force_refresh=False):
        periods, period_label = self.get_periods(download_type, fy, quarter, year, month)
        
        all_b2b = []
        all_cdnr = []
        
        errors = []
        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_period = {
                executor.submit(GSTDataService.get_gstr2b, gstin, yr, mn, taxpayer_token, force_refresh): (yr, mn) 
                for yr, mn in periods
            }
            
            for future in as_completed(future_to_period):
                period = future_to_period[future]
                try:
                    data = future.result()
                    results[period] = data
                except Exception as e:
                    errors.append(f"{period[1]:02d}-{period[0]}: {str(e)}")

        # Process results in specified chronological period order
        for yr, mn in periods:
            data = results.get((yr, mn))
            if data:
                b2b, cdnr = self.extract_data(data, period_str=f"{mn:02d}-{yr}")
                all_b2b.extend(b2b)
                all_cdnr.extend(cdnr)

        if not all_b2b and not all_cdnr and errors:
            raise Exception(f"Failed to fetch GSTR-2B data: {errors[0]}")
        
        df_b2b = pd.DataFrame(all_b2b)
        df_cdnr = pd.DataFrame(all_cdnr)
        
        cols = ["Return Period", "GSTIN/UIN", "Supplier", "Invoice", "Date", "Gross Amt", "Taxable", "IGST", "CGST", "SGST", "Cess", "Type"]
        num_fields = ["Gross Amt", "Taxable", "IGST", "CGST", "SGST", "Cess"]

        def process_df(df):
            if df.empty: return pd.DataFrame(columns=cols)
            for col in cols:
                if col not in df.columns: df[col] = None
            for col in num_fields:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            return df[cols]

        df_b2b = process_df(df_b2b)
        df_cdnr = process_df(df_cdnr)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_b2b.to_excel(writer, sheet_name='B2B_Data', index=False)
            df_cdnr.to_excel(writer, sheet_name='CDNR_Data', index=False)
        
        output.seek(0)
        filename = f"GSTR2_2B_{gstin}_{period_label}.xlsx"
        return output, filename
