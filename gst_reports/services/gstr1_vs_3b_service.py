# gst_reports/services/gstr1_vs_3b_service.py

from gst_reports.services.gst_data_service import GSTDataService

def get_val(source_dict, key, field):
    """
    Tries to fetch value from:
    1. source_dict[key]['subtotal'][field] (Auto-Pop style)
    2. source_dict[key][field] (Filed style)
    3. Returns 0.0 if not found
    """
    if not source_dict:
        return 0.0
        
    section = source_dict.get(key, {})
    if not section:
        return 0.0

    # Try Auto-Populated Structure (nested in subtotal)
    if "subtotal" in section:
        return float(section["subtotal"].get(field, 0) or 0)
    
    # Try Filed Structure (direct value)
    return float(section.get(field, 0) or 0)


def fetch_auto_liability(year, month, gstin, taxpayer_token, force_refresh=False):
    """Fetch auto-calculated GSTR-3B liability using cached data service."""
    data = GSTDataService.get_gstr3b_auto_liability(
        gstin=gstin,
        year=year,
        month=month,
        taxpayer_token=taxpayer_token,
        force_refresh=force_refresh
    )
    
    if not data:
        return None

    try:
        # data is already unwrapped by GSTDataService
        # Check for both possible structures (standard vs extra nested)
        inner = data
        if "data" in inner and isinstance(inner["data"], dict):
            inner = inner["data"]
            
        sup_details = inner.get("liabitc", {}).get("sup_details") or inner.get("r3bautopop", {}).get("liabitc", {}).get("sup_details", {})
    except:
        return None

    if not sup_details:
        return None

    return {
        "tx": get_val(sup_details, "osup_3_1a", "txval"),
        "igst": get_val(sup_details, "osup_3_1a", "iamt"),
        "cgst": get_val(sup_details, "osup_3_1a", "camt"),
        "sgst": get_val(sup_details, "osup_3_1a", "samt"),
        "exp_tx": get_val(sup_details, "osup_3_1b", "txval"),
        "exp_igst": get_val(sup_details, "osup_3_1b", "iamt"),
        "nil_tx": get_val(sup_details, "osup_3_1c", "txval"),
        "nongst_tx": get_val(sup_details, "osup_3_1e", "txval"),
    }


def fetch_filed_3b(year, month, gstin, taxpayer_token, force_refresh=False):
    """Fetch filed GSTR-3B data using cached data service."""
    data = GSTDataService.get_gstr3b_filed(
        gstin=gstin,
        year=year,
        month=month,
        taxpayer_token=taxpayer_token,
        force_refresh=force_refresh
    )
    
    if not data:
        return None

    try:
        # data is already unwrapped by GSTDataService
        inner = data
        if "data" in inner and isinstance(inner["data"], dict):
            inner = inner["data"]
            
        sup_details = inner.get("sup_details", {})
        itc_elg = inner.get("itc_elg", {})
    except:
        return None
        
    if not sup_details:
        return None

    itc_avl = itc_elg.get("itc_avl", [])
    
    itc_total_igst = 0
    itc_total_cgst = 0
    itc_total_sgst = 0
    itc_total_cess = 0
    
    itc_rcm_igst = 0
    itc_rcm_cgst = 0
    itc_rcm_sgst = 0
    itc_rcm_cess = 0
    
    for item in itc_avl:
        igst = float(item.get("iamt", 0) or 0)
        cgst = float(item.get("camt", 0) or 0)
        sgst = float(item.get("samt", 0) or 0)
        cess = float(item.get("csamt", 0) or 0)
        
        itc_total_igst += igst
        itc_total_cgst += cgst
        itc_total_sgst += sgst
        itc_total_cess += cess
        
        item_type = item.get("ty", "")
        if item_type in ["IMPG", "IMPS", "ISRC"]:
            itc_rcm_igst += igst
            itc_rcm_cgst += cgst
            itc_rcm_sgst += sgst
            itc_rcm_cess += cess

    return {
        "tx": get_val(sup_details, "osup_det", "txval"),
        "igst": get_val(sup_details, "osup_det", "iamt"),
        "cgst": get_val(sup_details, "osup_det", "camt"),
        "sgst": get_val(sup_details, "osup_det", "samt"),
        "exp_tx": get_val(sup_details, "osup_zero", "txval"),
        "exp_igst": get_val(sup_details, "osup_zero", "iamt"),
        "nil_tx": get_val(sup_details, "osup_nil_exmp", "txval"),
        "nongst_tx": get_val(sup_details, "osup_nongst", "txval"),
        "itc_igst": itc_total_igst,
        "itc_cgst": itc_total_cgst,
        "itc_sgst": itc_total_sgst,
        "itc_cess": itc_total_cess,
        "itc_rcm_igst": itc_rcm_igst,
        "itc_rcm_cgst": itc_rcm_cgst,
        "itc_rcm_sgst": itc_rcm_sgst,
        "itc_rcm_cess": itc_rcm_cess,
    }


def fetch_2b_data(year, month, gstin, taxpayer_token, force_refresh=False):
    """Fetch GSTR-2B ITC data using cached data service."""
    data = GSTDataService.get_gstr2b(
        gstin=gstin,
        year=year,
        month=month,
        taxpayer_token=taxpayer_token,
        force_refresh=force_refresh
    )
    
    defaults = {
        "itc_igst": 0, "itc_cgst": 0, "itc_sgst": 0, "itc_cess": 0,
        "b2b_igst": 0, "b2b_cgst": 0, "b2b_sgst": 0,
        "oth_igst": 0, "oth_cgst": 0, "oth_sgst": 0,
    }

    if not data:
        return defaults

    try:
        # Robust unwrapping and key checking
        inner = data
        if "data" in inner and isinstance(inner["data"], dict):
            inner = inner["data"]
            
        itcsumm = inner.get("itcsumm") or inner.get("itc_summ") or {}
        itcavl = itcsumm.get("itcavl", {})
        nonrevsup = itcavl.get("nonrevsup") or itcavl.get("non_rev_sup") or {}
        othersup = itcavl.get("othersup") or itcavl.get("other_sup") or {}
        
        def get_itc_vals(section):
            if not section: return 0, 0, 0, 0
            return (
                float(section.get("iamt") or section.get("igst") or 0),
                float(section.get("camt") or section.get("cgst") or 0),
                float(section.get("samt") or section.get("sgst") or 0),
                float(section.get("csamt") or section.get("cess") or 0)
            )
        
        nr_igst, nr_cgst, nr_sgst, nr_cess = get_itc_vals(nonrevsup)
        oth_igst, oth_cgst, oth_sgst, oth_cess = get_itc_vals(othersup)
        
        return {
            "itc_igst": nr_igst + oth_igst,
            "itc_cgst": nr_cgst + oth_cgst,
            "itc_sgst": nr_sgst + oth_sgst,
            "itc_cess": nr_cess + oth_cess,
            "b2b_igst": nr_igst,
            "b2b_cgst": nr_cgst,
            "b2b_sgst": nr_sgst,
            "oth_igst": oth_igst,
            "oth_cgst": oth_cgst,
            "oth_sgst": oth_sgst,
        }
    except Exception as e:
        import logging
        logging.error(f"Error parsing GSTR-2B data: {str(e)}")
        return defaults


def reconcile_gstr1_vs_3b(year, month, gstin, taxpayer_token, force_refresh=False):
    """Reconcile GSTR-1 vs GSTR-3B for a specific month."""
    auto = fetch_auto_liability(year, month, gstin, taxpayer_token, force_refresh)
    filed = fetch_filed_3b(year, month, gstin, taxpayer_token, force_refresh)
    gstr2b = fetch_2b_data(year, month, gstin, taxpayer_token, force_refresh)

    # Return partial data if any return is present, instead of returning None
    if not auto and not filed and not gstr2b:
        return None

    # Safe defaults if one side is missing
    auto_safe = auto or {
        "tx": 0, "igst": 0, "cgst": 0, "sgst": 0, "exp_tx": 0, 
        "exp_igst": 0, "nil_tx": 0, "nongst_tx": 0
    }
    filed_safe = filed or {
        "tx": 0, "igst": 0, "cgst": 0, "sgst": 0, "exp_tx": 0, 
        "exp_igst": 0, "nil_tx": 0, "nongst_tx": 0,
        "itc_igst": 0, "itc_cgst": 0, "itc_sgst": 0, "itc_cess": 0,
        "itc_rcm_igst": 0, "itc_rcm_cgst": 0, "itc_rcm_sgst": 0, "itc_rcm_cess": 0
    }
    
    sales_diff = (
        abs(auto_safe["tx"] - filed_safe["tx"]) +
        abs(auto_safe["igst"] - filed_safe["igst"]) +
        abs(auto_safe["cgst"] - filed_safe["cgst"]) +
        abs(auto_safe["sgst"] - filed_safe["sgst"]) +
        abs(auto_safe["exp_tx"] - filed_safe["exp_tx"]) +
        abs(auto_safe["nongst_tx"] - filed_safe["nongst_tx"])
    )

    g3_adj_igst = filed_safe["itc_igst"] - filed_safe.get("itc_rcm_igst", 0)
    g3_adj_cgst = filed_safe["itc_cgst"] - filed_safe.get("itc_rcm_cgst", 0)
    g3_adj_sgst = filed_safe["itc_sgst"] - filed_safe.get("itc_rcm_sgst", 0)
    g3_adj_cess = filed_safe["itc_cess"] - filed_safe.get("itc_rcm_cess", 0)
    
    if gstr2b and (gstr2b["itc_igst"] > 0 or gstr2b["itc_cgst"] > 0):
        itc_diff_adj = (
            abs(gstr2b["itc_igst"] - g3_adj_igst) +
            abs(gstr2b["itc_cgst"] - g3_adj_cgst) +
            abs(gstr2b["itc_sgst"] - g3_adj_sgst) +
            abs(gstr2b["itc_cess"] - g3_adj_cess)
        )
        
        has_rcm = (filed_safe.get("itc_rcm_igst", 0) + filed_safe.get("itc_rcm_cgst", 0) + 
                   filed_safe.get("itc_rcm_sgst", 0) + filed_safe.get("itc_rcm_cess", 0)) > 0
        
        has_excess = (g3_adj_igst - gstr2b["itc_igst"] > 5 or 
                      g3_adj_cgst - gstr2b["itc_cgst"] > 5 or 
                      g3_adj_sgst - gstr2b["itc_sgst"] > 5 or 
                      g3_adj_cess - gstr2b["itc_cess"] > 5)
        
        if has_excess:
            itc_status = "RISK"
        elif itc_diff_adj < 5.0:
            itc_status = "RECONCILED" if has_rcm else "MATCH"
        else:
            itc_status = "PARTIAL"
    else:
        itc_status = "NO 2B DATA" if (not gstr2b or (gstr2b["itc_igst"] == 0 and gstr2b["itc_cgst"] == 0)) else "MATCH"

    status = "MATCH" if sales_diff < 5.0 else "MISMATCH"
    if not auto or not filed:
        status = "NO DATA" if not auto and not filed else "INCOMPLETE"

    return {
        "year": year, "month": month,
        "auto_tx": auto_safe["tx"], "g3_tx": filed_safe["tx"],
        "auto_igst": auto_safe["igst"], "g3_igst": filed_safe["igst"],
        "auto_cgst": auto_safe["cgst"], "g3_cgst": filed_safe["cgst"],
        "auto_sgst": auto_safe["sgst"], "g3_sgst": filed_safe["sgst"],
        "auto_exp_tx": auto_safe["exp_tx"], "g3_exp_tx": filed_safe["exp_tx"],
        "auto_exp_igst": auto_safe["exp_igst"], "g3_exp_igst": filed_safe["exp_igst"],
        "auto_nil_tx": auto_safe["nil_tx"], "g3_nil_tx": filed_safe["nil_tx"],
        "auto_nongst_tx": auto_safe["nongst_tx"], "g3_nongst_tx": filed_safe["nongst_tx"],
        "sales_status": status,
        "g2b_itc_igst": gstr2b["itc_igst"] if gstr2b else 0,
        "g2b_itc_cgst": gstr2b["itc_cgst"] if gstr2b else 0,
        "g2b_itc_sgst": gstr2b["itc_sgst"] if gstr2b else 0,
        "g2b_itc_cess": gstr2b["itc_cess"] if gstr2b else 0,
        "g3_itc_igst": filed_safe["itc_igst"],
        "g3_itc_cgst": filed_safe["itc_cgst"],
        "g3_itc_sgst": filed_safe["itc_sgst"],
        "g3_itc_cess": filed_safe["itc_cess"],
        "g3_rcm_igst": filed_safe.get("itc_rcm_igst", 0),
        "g3_rcm_cgst": filed_safe.get("itc_rcm_cgst", 0),
        "g3_rcm_sgst": filed_safe.get("itc_rcm_sgst", 0),
        "g3_rcm_cess": filed_safe.get("itc_rcm_cess", 0),
        "g3_adj_igst": g3_adj_igst,
        "g3_adj_cgst": g3_adj_cgst,
        "g3_adj_sgst": g3_adj_sgst,
        "g3_adj_cess": g3_adj_cess,
        "itc_status": itc_status,
        "status": status
    }

def reconcile_comprehensive(year, month, gstin, taxpayer_token, force_refresh=False):
    """
    Comprehensive GSTR-1 vs 3B vs 2B Reconciliation.
    Fetches raw data for all three separately to ensure individual caching.
    """
    # These calls populate CachedGSTResponse via GSTDataService
    auto = fetch_auto_liability(year, month, gstin, taxpayer_token, force_refresh)
    filed = fetch_filed_3b(year, month, gstin, taxpayer_token, force_refresh)
    g2b = fetch_2b_data(year, month, gstin, taxpayer_token, force_refresh)

    if not auto and not filed and not g2b:
        return None

    # We use the existing logic to calculate the reconciliation
    recon = reconcile_gstr1_vs_3b(year, month, gstin, taxpayer_token, force_refresh)
    
    return {
        "period": f"{month:02d}-{year}",
        "summary": {
            "liability": {
                "r1": {"tx": recon["auto_tx"], "tax": recon["auto_igst"] + recon["auto_cgst"] + recon["auto_sgst"]},
                "g3": {"tx": recon["g3_tx"], "tax": recon["g3_igst"] + recon["g3_cgst"] + recon["g3_sgst"]},
                "status": recon["sales_status"]
            },
            "credit": {
                "g2b": {"tax": recon["g2b_itc_igst"] + recon["g2b_itc_cgst"] + recon["g2b_itc_sgst"]},
                "g3": {"tax": recon["g3_itc_igst"] + recon["g3_itc_cgst"] + recon["g3_itc_sgst"]},
                "status": recon["itc_status"]
            }
        },
        "detailed": recon
    }
