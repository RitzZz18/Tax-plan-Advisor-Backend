import pandas as pd
from pathlib import Path
import json
import datetime
import tempfile
import os

def build_report_excel(recon_result, job_id=None):
    """
    recon_result is output of reconcile_records.
    Produces an Excel file with:
      - Summary_Reconciliation
      - Invoice_Matches
      - Unmatched_GSTR1
      - Unmatched_GSTR3B
      - Raw JSON
    Returns path to file.
    """
    temp_dir = tempfile.gettempdir()
    out = os.path.join(temp_dir, f"recon_report_{job_id or 'local'}_{int(datetime.datetime.now().timestamp())}.xlsx")
    matches = recon_result.get('matches', [])
    df_matches = pd.DataFrame([{
        "invoice_gstr1": m['gstr1'].get('invoice_no'),
        "invoice_gstr3b": m['gstr3b'].get('invoice_no'),
        "taxable_gstr1": m['gstr1'].get('taxable_value'),
        "taxable_gstr3b": m['gstr3b'].get('taxable_value'),
        "taxable_diff": m['taxable_diff'],
        "igst_diff": m['igst_diff'],
        "cgst_diff": m['cgst_diff'],
        "sgst_diff": m['sgst_diff'],
        "match_method": m['method'],
        "status": m['status']
    } for m in matches])

    df_unmatched_g1 = pd.DataFrame(recon_result.get('unmatched_gstr1', []))
    df_unmatched_g3 = pd.DataFrame(recon_result.get('unmatched_gstr3b', []))
    df_summary = pd.DataFrame([recon_result.get('summary_deltas', {})])

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_summary.to_excel(writer, sheet_name="Summary_Reconciliation", index=False)
        df_matches.to_excel(writer, sheet_name="Invoice_Matches", index=False)
        df_unmatched_g1.to_excel(writer, sheet_name="Unmatched_GSTR1", index=False)
        df_unmatched_g3.to_excel(writer, sheet_name="Unmatched_GSTR3B", index=False)
        # raw JSON as a sheet
        pd.DataFrame([{"raw": json.dumps(recon_result)}]).to_excel(writer, sheet_name="Raw", index=False)
    return str(out)
