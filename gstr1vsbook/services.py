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
    def load_and_normalize_books(self, file_bytes, month_list):
        """Load Excel from bytes, normalize, and aggregate by GSTIN."""
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
            
            records.append({
                "GSTIN": r["GSTIN"],
                "POS_State": r["POS_State"],
                "SUPPLY_TYPE": supply_type,
                "Taxable": taxable_total,
                "IGST": r["IGST"],
                "CGST": r["CGST"],
                "SGST": r["SGST"],
                "Rate": rate
            })
        
        normalized = pd.DataFrame(records)
        if normalized.empty:
            return pd.DataFrame()

        # Aggregate
        grp = normalized.groupby(["GSTIN", "SUPPLY_TYPE", "POS_State", "Rate"], dropna=False)
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
                itm = inv["itms"][0]["itm_det"]
                rows.append({
                    "GSTIN": gstin,
                    "Taxable": self.r2(itm["txval"]),
                    "IGST": self.r2(itm.get("iamt", 0)),
                    "CGST": self.r2(itm.get("camt", 0)),
                    "SGST": self.r2(itm.get("samt", 0))
                })
        return pd.DataFrame(rows)

    def portal_rate_df(self, data):
        return pd.DataFrame([{
            "Rate": int(r.get("rt", 0)),
            "Taxable": self.r2(r.get("txval", 0)),
            "IGST": self.r2(r.get("iamt", 0)),
            "CGST": self.r2(r.get("camt", 0)),
            "SGST": self.r2(r.get("samt", 0))
        } for r in data])

    def portal_exp_df(self, data):
        rows = []
        for e in data:
            for inv in e.get("inv", []):
                itm = inv["itms"][0]
                rows.append({
                    "SUPPLY_TYPE": "EXPWP" if e["exp_typ"] == "WPAY" else "EXPWOP",
                    "Taxable": self.r2(itm["txval"]),
                    "IGST": self.r2(itm.get("iamt", 0))
                })
        return pd.DataFrame(rows)

    def portal_cdnr_df(self, data):
        rows = []
        for c in data:
            gstin = str(c.get("ctin", "")).strip()
            for nt in c.get("nt", []):
                itm = nt["itms"][0]["itm_det"]
                rows.append({
                    "GSTIN": gstin,
                    "Taxable": -self.r2(itm["txval"]),
                    "IGST": -self.r2(itm.get("iamt", 0)),
                    "CGST": -self.r2(itm.get("camt", 0)),
                    "SGST": -self.r2(itm.get("samt", 0))
                })
        return pd.DataFrame(rows)

    # =====================================================
    # RECONCILIATION
    # =====================================================
    def reconcile(self, books, portal, keys, tolerance=1.0):
        """
        Reconcile books with portal data.
        tolerance: Differences less than this amount (in Rs) are set to 0
        """
        if books.empty and portal.empty:
            return pd.DataFrame()
        
        value_cols = ["Taxable", "IGST", "CGST", "SGST"]
        
        agg_cols = [c for c in value_cols if c in books.columns]
        b = books.groupby(keys, dropna=False)[agg_cols].sum().reset_index() if not books.empty else pd.DataFrame(columns=keys + agg_cols)
        
        agg_cols_p = [c for c in value_cols if c in portal.columns]
        p = portal.groupby(keys, dropna=False)[agg_cols_p].sum().reset_index() if not portal.empty else pd.DataFrame(columns=keys + agg_cols_p)
        
        out = b.merge(p, on=keys, how="outer", suffixes=("_BOOKS", "_PORTAL")).fillna(0)
        
        diff_cols = []
        for c in value_cols:
            if c + "_BOOKS" in out and c + "_PORTAL" in out:
                diff_col = c + "_DIFF"
                out[diff_col] = out[c + "_BOOKS"] - out[c + "_PORTAL"]
                # Apply tolerance: set small differences to 0
                out.loc[out[diff_col].abs() < tolerance, diff_col] = 0
                diff_cols.append(diff_col)
        
        # Filter out rows where ALL differences are 0
        if diff_cols:
            has_diff = out[diff_cols].abs().sum(axis=1) > 0
            out = out[has_diff].reset_index(drop=True)
        
        return out

    # =====================================================
    # MAIN RUNNER
    # =====================================================
    def run(self, file_bytes, session_id, reco_type, year, month=None, quarter=None):
        """
        Main entry point. Returns a dict of DataFrames keyed by section name.
        """
        # TODO: Use session_id to get taxpayer token for API calls
        
        month_list = self.get_months_list(reco_type, year, month, quarter)
        if not month_list:
            raise ValueError("Invalid reconciliation type or parameters")
        
        books = self.load_and_normalize_books(file_bytes, month_list)
        
        results = {}
        
        # B2B
        b2b_books = books[books["SUPPLY_TYPE"] == "B2B"] if not books.empty else pd.DataFrame()
        b2b_portal = self.get_aggregated_portal_data("b2b", month_list, self.portal_b2b_df)
        results["B2B"] = self.reconcile(b2b_books, b2b_portal, ["GSTIN"])
        
        # B2CL
        b2cl_books = books[books["SUPPLY_TYPE"] == "B2CL"] if not books.empty else pd.DataFrame()
        b2cl_portal = self.get_aggregated_portal_data("b2cl", month_list, self.portal_rate_df)
        results["B2CL"] = self.reconcile(b2cl_books, b2cl_portal, ["Rate"])
        
        # B2CS
        b2cs_books = books[books["SUPPLY_TYPE"] == "B2CS"] if not books.empty else pd.DataFrame()
        b2cs_portal = self.get_aggregated_portal_data("b2cs", month_list, self.portal_rate_df)
        results["B2CS"] = self.reconcile(b2cs_books, b2cs_portal, ["Rate"])
        
        # EXPORT
        exp_books = books[books["SUPPLY_TYPE"].isin(["EXPWP", "EXPWOP"])] if not books.empty else pd.DataFrame()
        exp_portal = self.get_aggregated_portal_data("exp", month_list, self.portal_exp_df)
        results["EXP"] = self.reconcile(exp_books, exp_portal, ["SUPPLY_TYPE"])
        
        # CDNR
        cdnr_books = books[books["SUPPLY_TYPE"] == "CDNR"] if not books.empty else pd.DataFrame()
        cdnr_portal = self.get_aggregated_portal_data("cdnr", month_list, self.portal_cdnr_df)
        results["CDNR"] = self.reconcile(cdnr_books, cdnr_portal, ["GSTIN"])
        
        return results