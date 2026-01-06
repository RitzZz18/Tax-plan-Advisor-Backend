"""
GSTR-1 Reconciliation Service
Converts the standalone script into a reusable service class.
"""
import pandas as pd
import requests
import re
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from django.conf import settings


GSTIN_REGEX = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)
STANDARD_RATES = [0, 0.1, 0.25, 1, 1.5, 3, 5, 12, 18, 28]

STATE_CODE_MAP = {
    'JAMMU AND KASHMIR': '01', 'HIMACHAL PRADESH': '02', 'PUNJAB': '03', 'CHANDIGARH': '04', 'UTTARAKHAND': '05', 
    'HARYANA': '06', 'DELHI': '07', 'RAJASTHAN': '08', 'UTTAR PRADESH': '09', 'BIHAR': '10', 'SIKKIM': '11', 
    'ARUNACHAL PRADESH': '12', 'NAGALAND': '13', 'MANIPUR': '14', 'MIZORAM': '15', 'TRIPURA': '16', 'MEGHALAY': '17', 
    'ASSAM': '18', 'WEST BENGAL': '19', 'JHARKHAND': '20', 'ODISHA': '21', 'CHHATTISGARH': '22', 'MADHYA PRADESH': '23', 
    'GUJARAT': '24', 'DAMAN AND DIU': '25', 'DADRA AND NAGAR HAVELI': '26', 'MAHARASHTRA': '27', 'ANDHRA PRADESH': '28', 
    'KARNATAKA': '29', 'GOA': '30', 'LAKSHADWEEP': '31', 'KERALA': '32', 'TAMIL NADU': '33', 'PUDUCHERRY': '34', 
    'ANDAMAN AND NICOBAR ISLANDS': '35', 'TELANGANA': '36', 'ANDHRA PRADESH(NEW)': '37', 'LADAKH': '38', 'OTHER TERRITORY': '97'
}


class GSTR1ReconciliationService:
    """
    Service class for GSTR-1 Books vs Portal Reconciliation.
    """
    
    def __init__(self, api_key=None, access_token=None):
        # Use settings or passed credentials
        self.api_key = api_key or getattr(settings, 'GST_API_KEY', '')
        self.access_token = access_token or getattr(settings, 'GST_ACCESS_TOKEN', '')
        self.base_url = "https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-1"
        self.headers = {
            "x-api-version": "1.0.0",
            "Authorization": self.access_token,
            "x-api-key": self.api_key
        }
    
    # =====================================================
    # UTILITIES
    # =====================================================
    @staticmethod
    def r2(x):
        return float(Decimal(str(x or 0)).quantize(Decimal("0.01"), ROUND_HALF_UP))

    @staticmethod
    def is_valid_gstin(gstin: str) -> bool:
        if not gstin:
            return False
        return bool(GSTIN_REGEX.match(str(gstin).strip().upper()))

    @staticmethod
    def snap_to_standard_rate(raw_rate):
        return min(STANDARD_RATES, key=lambda x: abs(x - raw_rate))

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

    # =====================================================
    # DATA LOADING
    # =====================================================
    def load_and_normalize_books(self, file_bytes, month_list, business_gstin=None):
        """Load Excel from bytes, normalize, and aggregate by GSTIN."""
        default_pos = str(business_gstin)[:2] if business_gstin and len(str(business_gstin)) >= 2 else None

        try:
            df = pd.read_excel(BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {str(e)}")

        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors='coerce')
        df = df[df["Date"].apply(lambda d: (d.year, d.month) in month_list)].copy()
        
        if df.empty:
            return pd.DataFrame()

        # Clean
        df["GSTIN"] = df["GSTIN"].fillna("").astype(str).str.strip()
        df["Is_RCM"] = df["Is_RCM"].fillna("N").astype(str).str.upper()
        
        numeric_cols = ["Taxable", "Export_Taxable", "SEZ_Taxable", "Nil_Rated", 
                        "Exempt", "Non_GST", "IGST", "CGST", "SGST", "Rate"]
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        
        # Normalize
        records = []
        for _, r in df.iterrows():
            supply_type = self._derive_supply_type(r)
            if supply_type is None:
                continue
            
            taxable_total = r["Taxable"] + r["Export_Taxable"] + r["SEZ_Taxable"] + \
                            r["Nil_Rated"] + r["Exempt"] + r["Non_GST"]
            total_tax = r["IGST"] + r["CGST"] + r["SGST"]
            rate = r["Rate"]
            
            if rate == 0 and taxable_total > 0 and total_tax > 0:
                raw_rate = (total_tax / taxable_total) * 100
                rate = self.snap_to_standard_rate(raw_rate)
            
            # Clean POS
            pos = str(r.get("POS_State", "")).strip().upper()
            if not pos or pos == "NAN":
                pos = default_pos
            elif pos in STATE_CODE_MAP:
                pos = STATE_CODE_MAP[pos]
            elif pos.isdigit():
                pos = pos.zfill(2)

            records.append({
                "GSTIN": r["GSTIN"],
                "POS_State": pos,
                "SUPPLY_TYPE": supply_type,
                "Taxable": taxable_total,
                "IGST": r["IGST"],
                "CGST": r["CGST"],
                "SGST": r["SGST"],
                "Rate": rate,
                "Year": r["Date"].year,
                "Month": r["Date"].month
            })
        
        normalized = pd.DataFrame(records)
        if normalized.empty:
            return pd.DataFrame()

        # Aggregate for detail sheet
        grp = normalized.groupby(["GSTIN", "SUPPLY_TYPE", "POS_State", "Rate", "Year", "Month"], dropna=False)
        return grp[["Taxable", "IGST", "CGST", "SGST"]].sum().reset_index()

    def _derive_supply_type(self, r):
        tax_amount = r["IGST"] + r["CGST"] + r["SGST"]
        gstin = str(r["GSTIN"]).strip().upper()
        has_valid_gstin = self.is_valid_gstin(gstin)
        
        if r["Export_Taxable"] > 0: return "EXPWP" if tax_amount > 0 else "EXPWOP"
        if r["SEZ_Taxable"] > 0: return "SEZWP" if tax_amount > 0 else "SEZWOP"
        if str(r["Is_RCM"]).upper() == "Y": return "CDNR"
        if has_valid_gstin: return "B2B"
        if tax_amount > 0:
            return "B2CL" if (r["IGST"] > 0 and r["Taxable"] > 250000) else "B2CS"
        
        buckets = {"NIL": r["Nil_Rated"], "EXEMPT": r["Exempt"], "NON_GST": r["Non_GST"]}
        filled = [k for k, v in buckets.items() if v > 0]
        return filled[0] if filled else None

    # =====================================================
    # PORTAL FETCHING
    # =====================================================
    def fetch_portal(self, section, year, month):
        url = f"{self.base_url}/{section}/{year}/{month:02d}"
        try:
            r = requests.get(url, headers=self.headers, timeout=30)
            if r.status_code != 200:
                return []
            return r.json().get("data", {}).get("data", {}).get(section, [])
        except Exception:
            return []

    def get_aggregated_portal_data(self, section, month_list, parser_func):
        frames = []
        for year, month in month_list:
            raw_data = self.fetch_portal(section, year, month)
            if raw_data:
                df = parser_func(raw_data)
                if not df.empty:
                    frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # =====================================================
    # PORTAL PARSERS
    # =====================================================
    def portal_b2b_df(self, data):
        rows = []
        for c in data:
            gstin = str(c["ctin"]).strip()
            for inv in c.get("inv", []):
                inv_typ = inv.get("inv_typ", "R")
                # Map SEZ types
                if inv_typ == "SEWP": sup_type = "SEZWP"
                elif inv_typ == "SEWOP": sup_type = "SEZWOP"
                else: sup_type = "B2B"
                
                for itm_wrap in inv.get("itms", []):
                    itm = itm_wrap.get("itm_det", {})
                    rows.append({
                        "GSTIN": gstin,
                        "SUPPLY_TYPE": sup_type,
                        "Taxable": self.r2(itm.get("txval", 0)),
                        "IGST": self.r2(itm.get("iamt", 0)),
                        "CGST": self.r2(itm.get("camt", 0)),
                        "SGST": self.r2(itm.get("samt", 0))
                    })
        return pd.DataFrame(rows)

    def portal_rate_df(self, data):
        rows = []
        for r in data:
            rows.append({
                "Rate": float(r.get("rt", 0)),
                "POS_State": str(r.get("pos", "")).strip(),
                "Taxable": self.r2(r.get("txval", 0)),
                "IGST": self.r2(r.get("iamt", 0)),
                "CGST": self.r2(r.get("camt", 0)),
                "SGST": self.r2(r.get("samt", 0))
            })
        return pd.DataFrame(rows)

    def portal_exp_df(self, data):
        rows = []
        for e in data:
            exp_typ = e.get("exp_typ", "WOPAY")
            sup_type = "EXPWP" if exp_typ == "WPAY" else "EXPWOP"
            for inv in e.get("inv", []):
                for itm in inv.get("itms", []):
                    rows.append({
                        "SUPPLY_TYPE": sup_type,
                        "Taxable": self.r2(itm.get("txval", 0)),
                        "IGST": self.r2(itm.get("iamt", 0))
                    })
        return pd.DataFrame(rows)

    def portal_cdnr_df(self, data):
        rows = []
        for c in data:
            gstin = str(c.get("ctin", "")).strip()
            for nt in c.get("nt", []):
                for itm_wrap in nt.get("itms", []):
                    itm = itm_wrap.get("itm_det", {})
                    rows.append({
                        "GSTIN": gstin,
                        "Taxable": -self.r2(itm.get("txval", 0)),
                        "IGST": -self.r2(itm.get("iamt", 0)),
                        "CGST": -self.r2(itm.get("camt", 0)),
                        "SGST": -self.r2(itm.get("samt", 0))
                    })
        return pd.DataFrame(rows)

    # =====================================================
    # RECONCILIATION
    # =====================================================
    def reconcile(self, books, portal, keys, tolerance=1.0, filter_matched=False):
        """
        Reconcile books with portal data.
        tolerance: Differences less than this amount (in Rs) are set to 0
        filter_matched: If True, only returns rows with differences
        """
        if books.empty and portal.empty:
            return pd.DataFrame()
        
        value_cols = ["Taxable", "IGST", "CGST", "SGST"]
        
        # Merge keys should include Year and Month if available in books
        merge_keys = list(keys)
        has_period = "Year" in books.columns and "Month" in books.columns
        if has_period:
            if "Year" not in merge_keys: merge_keys.append("Year")
            if "Month" not in merge_keys: merge_keys.append("Month")

        # Ensure consistent types for keys to avoid mismatch
        def clean_df_keys(df):
            if df.empty: return df
            if "Rate" in df.columns:
                df["Rate"] = pd.to_numeric(df["Rate"], errors='coerce').fillna(0).astype(float).round(2)
            if "Year" in df.columns:
                df["Year"] = pd.to_numeric(df["Year"], errors='coerce').fillna(0).astype(int)
            if "Month" in df.columns:
                df["Month"] = pd.to_numeric(df["Month"], errors='coerce').fillna(0).astype(int)
            if "POS_State" in df.columns:
                df["POS_State"] = df["POS_State"].fillna("").astype(str).str.strip().str.upper()
                # Remove decimal if it happened (e.g. "27.0" -> "27")
                df["POS_State"] = df["POS_State"].apply(lambda x: x.split('.')[0] if '.' in x else x).str.zfill(2)
            return df

        books = clean_df_keys(books)
        portal = clean_df_keys(portal)

        # Ensure portal has the columns too, even if empty
        if not portal.empty:
            for k in merge_keys:
                if k not in portal.columns:
                    portal[k] = "" if isinstance(k, str) else 0
        else:
            portal = pd.DataFrame(columns=merge_keys + value_cols)

        agg_cols = [c for c in value_cols if c in books.columns]
        b = books.groupby(merge_keys, dropna=False)[agg_cols].sum().reset_index() if not books.empty else pd.DataFrame(columns=merge_keys + agg_cols)
        
        agg_cols_p = [c for c in value_cols if c in portal.columns]
        p = portal.groupby(merge_keys, dropna=False)[agg_cols_p].sum().reset_index() if not portal.empty else pd.DataFrame(columns=merge_keys + agg_cols_p)
        
        out = b.merge(p, on=merge_keys, how="outer", suffixes=("_BOOKS", "_PORTAL")).fillna(0)
        
        diff_cols = []
        for c in value_cols:
            if c + "_BOOKS" in out and c + "_PORTAL" in out:
                diff_col = c + "_DIFF"
                out[diff_col] = out[c + "_BOOKS"] - out[c + "_PORTAL"]
                # Apply tolerance: set small differences to 0
                out.loc[out[diff_col].abs() < tolerance, diff_col] = 0
                diff_cols.append(diff_col)
        
        # Add Status Column (Vectorized for efficiency)
        if not out.empty and diff_cols:
            abs_sum_diff = out[diff_cols].abs().sum(axis=1)
            out["Status"] = "Matched"
            out.loc[abs_sum_diff >= tolerance, "Status"] = "Mismatch"

        # Filter out rows where ALL differences are 0 if requested
        if filter_matched and diff_cols:
            has_diff = out[diff_cols].abs().sum(axis=1) > 0
            out = out[has_diff].reset_index(drop=True)
        
        return out

    def get_monthly_summary(self, reco_results, month_list):
        """
        Generates a summary for GSTR-3B style cards.
        reco_results: { 'B2B': df, 'B2CL': df, ... }
        """
        summary = []
        sections = ["B2B", "B2CL", "B2CS", "EXP", "SEZ", "CDNR"]
        
        for year, month in month_list:
            m_key = f"{year}-{month:02d}"
            import datetime
            dt = datetime.datetime(year, month, 1)
            month_display = dt.strftime("%b %Y")
            
            rows = []
            m_status = "MATCHED"
            
            for section in sections:
                df = reco_results.get(section, pd.DataFrame())
                if df.empty:
                    v1, v2, diff = 0, 0, 0
                else:
                    # Filter by month/year if cols exist
                    mask = (df["Year"] == year) & (df["Month"] == month) if ("Year" in df.columns and "Month" in df.columns) else True
                    m_df = df[mask]
                    
                    # Sum up Taxable
                    v1 = m_df["Taxable_BOOKS"].sum() if "Taxable_BOOKS" in m_df.columns else 0
                    v2 = m_df["Taxable_PORTAL"].sum() if "Taxable_PORTAL" in m_df.columns else 0
                    diff = v1 - v2

                if abs(diff) > 1.0:
                    m_status = "MISMATCHED"
                    
                rows.append({
                    "particular": f"Total {section} (Taxable)",
                    "v1": v1,
                    "v2": v2,
                    "diff": diff
                })

            summary.append({
                "month": month_display,
                "month_key": m_key,
                "status": m_status,
                "rows": rows
            })
            
        return summary

    # =====================================================
    # MAIN RUNNER
    # =====================================================
    def run(self, file_bytes, session_id, reco_type, year, month=None, quarter=None, business_gstin=None):
        """
        Main entry point. Returns a dict of DataFrames keyed by section name + summary.
        """
        month_list = self.get_months_list(reco_type, year, month, quarter)
        if not month_list:
            raise ValueError("Invalid reconciliation type or parameters")
        
        books = self.load_and_normalize_books(file_bytes, month_list, business_gstin)

        
        # Helper to add Year/Month to portal dataframes
        def add_period(df, y, m):
            if df.empty: return df
            df["Year"] = y
            df["Month"] = m
            return df

        # Fetch Portal Data per month to keep Year/Month info
        b2b_p_frames = []
        b2cl_p_frames = []
        b2cs_p_frames = []
        exp_p_frames = []
        cdnr_p_frames = []

        for y, m in month_list:
            b2b_raw = self.fetch_portal("b2b", y, m)
            if b2b_raw: b2b_p_frames.append(add_period(self.portal_b2b_df(b2b_raw), y, m))
            
            b2cl_raw = self.fetch_portal("b2cl", y, m)
            if b2cl_raw: b2cl_p_frames.append(add_period(self.portal_rate_df(b2cl_raw), y, m))
            
            b2cs_raw = self.fetch_portal("b2cs", y, m)
            if b2cs_raw: b2cs_p_frames.append(add_period(self.portal_rate_df(b2cs_raw), y, m))
            
            exp_raw = self.fetch_portal("exp", y, m)
            if exp_raw: exp_p_frames.append(add_period(self.portal_exp_df(exp_raw), y, m))
            
            cdnr_raw = self.fetch_portal("cdnr", y, m)
            if cdnr_raw: cdnr_p_frames.append(add_period(self.portal_cdnr_df(cdnr_raw), y, m))

        b2b_portal = pd.concat(b2b_p_frames, ignore_index=True) if b2b_p_frames else pd.DataFrame()
        b2cl_portal = pd.concat(b2cl_p_frames, ignore_index=True) if b2cl_p_frames else pd.DataFrame()
        b2cs_portal = pd.concat(b2cs_p_frames, ignore_index=True) if b2cs_p_frames else pd.DataFrame()
        exp_portal = pd.concat(exp_p_frames, ignore_index=True) if exp_p_frames else pd.DataFrame()
        cdnr_portal = pd.concat(cdnr_p_frames, ignore_index=True) if cdnr_p_frames else pd.DataFrame()

        results = {}
        
        # B2B
        b2b_books = books[books["SUPPLY_TYPE"] == "B2B"] if not books.empty else pd.DataFrame()
        b2b_p_filtered = b2b_portal[b2b_portal["SUPPLY_TYPE"] == "B2B"] if not b2b_portal.empty else pd.DataFrame()
        results["B2B"] = self.reconcile(b2b_books, b2b_p_filtered, ["GSTIN"])
        
        # B2CL
        b2cl_books = books[books["SUPPLY_TYPE"] == "B2CL"] if not books.empty else pd.DataFrame()
        results["B2CL"] = self.reconcile(b2cl_books, b2cl_portal, ["Rate", "POS_State"])
        
        # B2CS
        b2cs_books = books[books["SUPPLY_TYPE"] == "B2CS"] if not books.empty else pd.DataFrame()
        results["B2CS"] = self.reconcile(b2cs_books, b2cs_portal, ["Rate", "POS_State"])
        
        # EXPORT
        exp_books = books[books["SUPPLY_TYPE"].isin(["EXPWP", "EXPWOP"])] if not books.empty else pd.DataFrame()
        results["EXP"] = self.reconcile(exp_books, exp_portal, ["SUPPLY_TYPE"])
        
        # SEZ
        sez_books = books[books["SUPPLY_TYPE"].isin(["SEZWP", "SEZWOP"])] if not books.empty else pd.DataFrame()
        sez_p_filtered = b2b_portal[b2b_portal["SUPPLY_TYPE"].isin(["SEZWP", "SEZWOP"])] if not b2b_portal.empty else pd.DataFrame()
        results["SEZ"] = self.reconcile(sez_books, sez_p_filtered, ["GSTIN"])

        # CDNR
        cdnr_books = books[books["SUPPLY_TYPE"] == "CDNR"] if not books.empty else pd.DataFrame()
        results["CDNR"] = self.reconcile(cdnr_books, cdnr_portal, ["GSTIN"])
        
        # Monthly Summary
        results["summary"] = self.get_monthly_summary(results, month_list)
        
        return results