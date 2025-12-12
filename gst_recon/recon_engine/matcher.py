from rapidfuzz import fuzz, process
from .config import PER_INVOICE_TOLERANCE, FUZZY_INVOICE_LEV_THRESHOLD, DATE_WINDOW_DAYS
from datetime import datetime, timedelta
from collections import defaultdict
import math

def reconcile_records(g1_rows, g3_rows, g1_summary=None, g3_summary=None):
    """
    :param g1_rows: list of dict invoice rows from GSTR1
    :param g3_rows: list of dict invoice rows from GSTR3B (usually empty as GSTR3B is summary-only)
    :returns: dict reconciliation result with invoice_matches, unmatched lists, summary_deltas
    """
    # GSTR-3B is typically summary-only, so we compare summaries
    s1 = g1_summary or aggregate_summary(g1_rows)
    s3 = g3_summary or aggregate_summary(g3_rows)
    
    print(f"DEBUG Matcher: GSTR1 Summary: {s1}")
    print(f"DEBUG Matcher: GSTR3B Summary: {s3}")
    
    # Category-wise breakdown for GSTR-1
    g1_categories = categorize_gstr1(g1_rows)
    g3_categories = categorize_gstr3b(g3_rows)
    
    # If GSTR3B has invoice-level data, do invoice matching
    matches = []
    unmatched_g1 = []
    unmatched_g3_rows = []
    
    if g3_rows and len(g3_rows) > 0:
        # Build quick lookup by (invoice_no, amount)
        g3_index = {}
        for r in g3_rows:
            key = (r.get('invoice_no','').strip().lower(), round(float(r.get('taxable_value',0)),2))
            g3_index.setdefault(key, []).append(r)

        unmatched_g3 = set([id(r) for r in g3_rows])

        # Exact & invoice_no+amount matching
        for r1 in g1_rows:
            key = (r1.get('invoice_no','').strip().lower(), round(float(r1.get('taxable_value',0)),2))
            cand = g3_index.get(key)
            if cand:
                r3 = cand.pop(0)
                matches.append(_make_match(r1, r3, method="EXACT"))
                unmatched_g3.discard(id(r3))
            else:
                unmatched_g1.append(r1)

        unmatched_g3_rows = [r for r in g3_rows if id(r) in unmatched_g3]
    else:
        # GSTR3B has no invoice data - all GSTR1 invoices are "unmatched" at detail level
        # But we show summary comparison
        unmatched_g1 = g1_rows

    # Build summary deltas
    summary_deltas = {
        "total_taxable_delta": round(float(s1.get('total_taxable',0) or 0) - float(s3.get('total_taxable',0) or 0),2),
        "igst_delta": round(float(s1.get('igst',0) or 0) - float(s3.get('igst',0) or 0),2),
        "cgst_delta": round(float(s1.get('cgst',0) or 0) - float(s3.get('cgst',0) or 0),2),
        "sgst_delta": round(float(s1.get('sgst',0) or 0) - float(s3.get('sgst',0) or 0),2)
    }
    
    # Determine reconciliation status
    is_reconciled = all(abs(v) < 1 for v in summary_deltas.values())

    return {
        "matches": matches,
        "unmatched_gstr1": unmatched_g1,
        "unmatched_gstr3b": unmatched_g3_rows,
        "summary_deltas": summary_deltas,
        "gstr1_summary": s1,
        "gstr3b_summary": s3,
        "gstr1_categories": g1_categories,
        "gstr3b_categories": g3_categories,
        "is_reconciled": is_reconciled,
        "reconciliation_note": "GSTR-3B is summary-only. Comparison is at summary level." if not g3_rows else "Invoice-level comparison completed."
    }

def categorize_gstr1(rows):
    """Categorize GSTR-1 rows into B2B, B2C, Export, etc."""
    categories = {
        "B2B": {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0, "records": 0},
        "B2C": {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0, "records": 0},
        "Export": {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0, "records": 0},
        "CDNR": {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0, "records": 0},
        "Others": {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0, "records": 0}
    }
    
    for row in rows:
        desc = row.get('invoice_no', '').lower()
        cat = "Others"
        
        if 'b2b' in desc or '4a' in desc or '4b' in desc or '4c' in desc:
            cat = "B2B"
        elif 'b2c' in desc or '5a' in desc or '5b' in desc or '7' in desc:
            cat = "B2C"
        elif 'export' in desc or '6a' in desc or '6b' in desc or '6c' in desc:
            cat = "Export"
        elif 'credit' in desc or 'debit' in desc or '9b' in desc or '9c' in desc:
            cat = "CDNR"
        
        categories[cat]["taxable"] += row.get('taxable_value', 0)
        categories[cat]["igst"] += row.get('igst', 0)
        categories[cat]["cgst"] += row.get('cgst', 0)
        categories[cat]["sgst"] += row.get('sgst', 0)
        categories[cat]["records"] += row.get('record_count', 0)
    
    return categories

def categorize_gstr3b(rows):
    """Categorize GSTR-3B rows into 3.1(a), 3.1(b), etc."""
    categories = {
        "3.1(a) - Outward Taxable": {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0},
        "3.1(b) - Zero Rated": {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0},
        "Others": {"taxable": 0, "igst": 0, "cgst": 0, "sgst": 0}
    }
    
    for row in rows:
        desc = row.get('invoice_no', '').lower()
        cat = "Others"
        
        if 'outward taxable' in desc or '(a)' in desc:
            cat = "3.1(a) - Outward Taxable"
        elif 'zero rated' in desc or '(b)' in desc:
            cat = "3.1(b) - Zero Rated"
        
        categories[cat]["taxable"] += row.get('taxable_value', 0)
        categories[cat]["igst"] += row.get('igst', 0)
        categories[cat]["cgst"] += row.get('cgst', 0)
        categories[cat]["sgst"] += row.get('sgst', 0)
    
    return categories

def _make_match(r1, r3, method="EXACT"):
    # compute diffs
    taxable_diff = round(float(r1.get('taxable_value',0) or 0) - float(r3.get('taxable_value',0) or 0),2)
    igst_diff = round(float(r1.get('igst',0) or 0) - float(r3.get('igst',0) or 0),2)
    cgst_diff = round(float(r1.get('cgst',0) or 0) - float(r3.get('cgst',0) or 0),2)
    sgst_diff = round(float(r1.get('sgst',0) or 0) - float(r3.get('sgst',0) or 0),2)

    status = "MATCH" if all(abs(x) <= PER_INVOICE_TOLERANCE for x in [taxable_diff, igst_diff, cgst_diff, sgst_diff]) else "VALUE_MISMATCH"

    return {
        "gstr1": r1,
        "gstr3b": r3,
        "taxable_diff": taxable_diff,
        "igst_diff": igst_diff,
        "cgst_diff": cgst_diff,
        "sgst_diff": sgst_diff,
        "method": method,
        "status": status
    }

def aggregate_summary(rows):
    tot = {"total_taxable":0,"igst":0,"cgst":0,"sgst":0}
    for r in rows:
        tot["total_taxable"] += float(r.get('taxable_value',0) or 0)
        tot["igst"] += float(r.get('igst',0) or 0)
        tot["cgst"] += float(r.get('cgst',0) or 0)
        tot["sgst"] += float(r.get('sgst',0) or 0)
    return tot
