import requests
import json
import pandas as pd
import time
from datetime import datetime
import os

# Constants
BASE_URL = "https://api.sandbox.co.in"

def get_platform_token(api_key, api_secret):
    """
    Authenticates with the Sandbox Platform to get the JWT Access Token.
    """
    url = f"{BASE_URL}/authenticate"
    headers = {
        "x-api-key": api_key,
        "x-api-secret": api_secret,
        "x-api-version": "1.0",
        "x-source": "primary"
    }
    
    print(f"Authenticating with Platform... {url}")
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Error in Platform Authentication: {e}")
        if response is not None:
             print(f"Response: {response.text}")
        return None

def request_gst_otp(access_token, api_key, gstin, username):
    """
    Requests OTP for GST User Authentication.
    """
    url = f"{BASE_URL}/gst/compliance/tax-payer/otp"
    headers = {
        "Authorization": access_token,
        "x-api-key": api_key,
        "x-api-version": "1.0",
        "Content-Type": "application/json",
        "x-source": "primary"
    }
    payload = {
        "gstin": gstin,
        "username": username
    }
    
    print(f"Requesting GST OTP for {gstin} ({username})...")
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        print("OTP Request Successful.")
        return data.get("transaction_id") # Note: Sandbox might return different fields, capturing mostly for debug
    except requests.exceptions.RequestException as e:
        print(f"Error requesting OTP: {e}")
        print(f"Response: {response.text}")
        return None

def verify_gst_otp(access_token, api_key, gstin, username, otp):
    """
    Verifies the GST OTP to establish a session.
    """
    url = f"{BASE_URL}/gst/compliance/tax-payer/otp/verify"
    headers = {
        "Authorization": access_token,
        "x-api-key": api_key,
        "x-api-version": "1.0",
        "Content-Type": "application/json",
        "x-source": "primary"
    }
    payload = {
        "gstin": gstin,
        "username": username,
        "otp": otp
    }
    
    
    print(f"Verifying OTP...")
    try:
        # Tried: JSON body only -> Failed with "Missing required request parameters: [otp]"
        # Fix: Search results suggest OTP might be a query parameter for this endpoint.
        # Sending in BOTH query params and JSON just in case.
        params = {"otp": otp}
        response = requests.post(url, headers=headers, json=payload, params=params)
        response.raise_for_status()
        print("OTP Verified. Session Active.")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error verifying OTP: {e}")
        print(f"Response: {response.text}")
        return None

def fetch_gstr2a_data(access_token, api_key, gstin, financial_year):
    """
    Fetches GSTR-2A data for all months in the given financial year.
    Returns a dictionary of DataFrames.
    """
    # Define months for the FY. Assuming FY format like "2023-24" or just strict months.
    # For simplicity, let's just ask for specific months or standard 12 months.
    # We will iterate standard calendar months for now or ask user.
    # Let's assume the user wants the data for a specific range.
    
    # Sections to fetch based on user request and image
    # Added: impgsez, tcs, tds, amdhist
    sections = [
        "b2b", "b2ba", 
        "cdn", "cdna", 
        "isd", 
        "impg", "impgsez", 
        "tcs", "tds", 
        # "amdhist" # Requires 'port_code', likely for Import Amendments. Disabling to prevent 400 error for general download.
    ]
    
    # We need to structure the data for Excel.
    # Approach: Dictionary { "Month_Section": DataFrame } or just { "Month": { "b2b": ..., "cdn": ... } }
    # User Request: "give an excel download for the sheet of the json data of 2a monthly"
    # Likely format: One Excel file. Sheets: "April-B2B", "April-CDN" OR "April" (merged? no, structure differs).
    # Best for analysis: 'B2B_Master', 'CDN_Master' containing all months with a 'Month' column.
    
    all_data = {section: [] for section in sections}
    
    start_year = int(financial_year.split('-')[0])
    
    # Standard Indian FY: April to March
    months_map = [
        ("04", start_year), #("05", start_year), ("06", start_year),
        # ("07", start_year), ("08", start_year), ("09", start_year),
        # ("10", start_year), ("11", start_year), ("12", start_year),
        # ("01", start_year + 1), ("02", start_year + 1), ("03", start_year + 1)
    ]
    
    headers = {
        "Authorization": access_token,
        "x-api-key": api_key,
        "x-api-version": "1.0",
        "gstin": gstin,
        "x-source": "primary"
    }

    for month, year in months_map:
        period = f"{month}{year}"
        print(f"Fetching GSTR-2A data for {period}...")
        
        for section in sections:
            # Endpoint structure from research: /gst/compliance/tax-payer/gstrs/gstr-2a/{section}/{year}/{month}
            # Re-verifying endpoint from search result [2]: .../gstr-2a/b2b/{year}/{month} -> unclear if year is full YYYY or FY.
            # Usually strict GSTN API uses MMYYYY as ret_period. 
            # Sandbox URL pattern: /gstr-2a/{section}?year=2024&month=04 OR path params.
            # Search result [1] says: .../gstr-2a/amdhist/{year}/{month}
            # Let's try path params as per search result.
            
            # Note: Search result says {year} and {month}. 
            # Is year 2024 or 2023-24? Usually it's calendar year for path params if month is separate.
            url = f"{BASE_URL}/gst/compliance/tax-payer/gstrs/gstr-2a/{section}?year={year}&month={month}"
            # Actually, standard REST design in Sandbox often puts them as path params:
            # .../gstrs/gstr-2a/{section}/{year}/{month}?gstin=...
            # But the search result 2 specifically showed path... let's try strict path.
            # Actually, to be safe, I will stick to the most common pattern or try-catch.
            
            # Let's assume: https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-2a/{section}?gstin={gstin}&year={year}&month={month}
            # Wait, Search Result 1: .../gstr-2a/amdhist/{year}/{month}
            # So:
            url = f"{BASE_URL}/gst/compliance/tax-payer/gstrs/gstr-2a/{section}"
            
            # Query Params are safer if documentation is ambiguous on path structure
            params = {
                "gstin": gstin,
                "year": year,
                "month": month
            }
            
            try:
                # IMPORTANT: Sandbox often uses 'ret_period' in some endpoints, but 'year'/'month' in others.
                # If the search result was explicit about path, I should use path.
                # Search result [3]: .../gstrs/gstr-2a/{year}/{month}
                # Let's try constructing the path.
                url_path = f"{BASE_URL}/gst/compliance/tax-payer/gstrs/gstr-2a/{section}"
                
                # We will send GET with params, if that fails, we can't easily retry in a script without logic.
                # Let's trust the params approach first as it's more standard for filters.
                # ACTUALLY, checking standard Sandbox docs pattern again mentally... 
                # They often map 1:1 to GSTN public APIs which use `ret_period=MMYYYY`.
                # But Sandbox wraps them. 
                # Let's use `ret_period` AND `year/month` to cover bases? No that's messy.
                # Let's look at the "GSTR-2A Document" search result again.
                # `.../gstr-2a/{year}/{month}`
                # So I'll use Path Params.
                
                req_url = f"{BASE_URL}/gst/compliance/tax-payer/gstrs/gstr-2a/{section}/{year}/{month}"
                
                # Headers need to be correct.
                # Sometimes `gstin` is required in header.
                
                res = requests.get(req_url, headers=headers, params={"gstin": gstin}) 
                # Adding gstin to params too just in case.
                
                if res.status_code == 200:
                    data = res.json()
                    # DEBUG: Print data structure for the first successful hit to debug "No Data"
                    # print(f"  [DEBUG] Raw Response for {section}: {str(data)[:200]}...")
                    
                    payload = data.get("data", {})
                    records = []
                    
                    # 1. Try finding section directly in payload (e.g. data['b2b'])
                    if isinstance(payload, dict) and section in payload:
                        records = payload[section]
                    
                    # 2. Try finding section in nested 'data' (e.g. data['data']['b2b']) - Sandbox pattern
                    elif isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], dict) and section in payload["data"]:
                        records = payload["data"][section]
                        
                    if records:
                        print(f"  -> Found {len(records)} records for {section}")
                        # Flatten B2B/CDN structure which is nested (CTIN -> Invoices -> Items)
                        if section in ["b2b", "b2ba", "cdn", "cdna"]:
                             for supplier in records:
                                 # Common fields like ctin, cfs
                                 supplier_meta = {k:v for k,v in supplier.items() if k not in ["inv", "nt"]}
                                 
                                 # B2B/B2BA uses 'inv'
                                 if "inv" in supplier:
                                     for inv in supplier["inv"]:
                                         # Extract common invoice fields, excluding 'itms'
                                         inv_meta = {k:v for k,v in inv.items() if k != "itms"}
                                         
                                         # Iterate through items to get tax details
                                         if "itms" in inv:
                                             for item in inv["itms"]:
                                                 itm_det = item.get("itm_det", {})
                                                 # Combine all levels: Supplier + Invoice + Item Details
                                                 flat_record = {
                                                     **supplier_meta, 
                                                     **inv_meta, 
                                                     **itm_det, # Explode tax details (rt, txval, iamt, etc.)
                                                     "Period": period
                                                 }
                                                 all_data[section].append(flat_record)
                                         else:
                                             # Fallback if no items but invoice exists
                                             flat_record = {**supplier_meta, **inv_meta, "Period": period}
                                             all_data[section].append(flat_record)
                                         
                                 # CDN/CDNA uses 'nt' (notes)
                                 elif "nt" in supplier:
                                     for note in supplier["nt"]:
                                          # Extract common note fields, excluding 'itms'
                                          note_meta = {k:v for k,v in note.items() if k != "itms"}
                                          
                                          if "itms" in note:
                                             for item in note["itms"]:
                                                 itm_det = item.get("itm_det", {})
                                                 flat_record = {
                                                     **supplier_meta, 
                                                     **note_meta, 
                                                     **itm_det,
                                                     "Period": period
                                                 }
                                                 all_data[section].append(flat_record)
                                          else:
                                              flat_record = {**supplier_meta, **note_meta, "Period": period}
                                              all_data[section].append(flat_record)
                        else:
                             # For other flat sections
                             for item in records:
                                 item["Period"] = period
                                 all_data[section].append(item)
                    
                else:
                    # If 404/403, might be no data or perm issue.
                    # Parse error message for clarity
                    try:
                        err_msg = res.json().get("message", res.text)
                    except:
                        err_msg = res.text
                    print(f"  [!] Failed to fetch {section}: {res.status_code} - {err_msg[:100]}")
                    
            except Exception as e:
                print(f"  [x] Error fetching {section} for {period}: {e}")
            
            time.sleep(0.5) # Rate limiting courtesy

    return all_data

def fetch_supplier_names(gstin_list, access_token, api_key):
    """
    Fetches Trade Name for a list of GSTINs using the Public Search API.
    """
    gstin_map = {}
    unique_gstins = list(set(gstin_list))
    print(f"Fetching names for {len(unique_gstins)} unique suppliers...")
    
    url = f"{BASE_URL}/gst/compliance/public/gstin/search"
    headers = {
        "Authorization": access_token, # Platform token is likely sufficient for public APIs
        "x-api-key": api_key,
        "x-api-version": "1.0",
        "Content-Type": "application/json",
        "x-source": "primary"
    }

    for idx, gstin in enumerate(unique_gstins):
        if not gstin: continue
        print(f"  [{idx+1}/{len(unique_gstins)}] Searching {gstin}...", end="\r")
        try:
             # Using parameters found in research: POST
             resp = requests.post(url, headers=headers, json={"gstin": gstin})
             if resp.status_code == 200:
                  d = resp.json()
                  if "data" in d and isinstance(d["data"], dict) and "data" in d["data"]:
                       inner_data = d["data"]["data"]
                       # 'tradeNam' or 'lgnm' - prefer Trade Name
                       name = inner_data.get("tradeNam") or inner_data.get("lgnm")
                       gstin_map[gstin] = name
        except Exception as e:
             pass
        time.sleep(0.2) # Rate limit courtesy
    
    print(f"\nFetched {len(gstin_map)} names.")
    return gstin_map

def process_and_save_excel(all_data, output_file="GSTR_2A_Data.xlsx"):
    """
    Saves the collected data into an Excel file with multiple sheets.
    """
    print(f"Processing data and saving to {output_file}...")
    
    # Column Mapping for User Friendly Names
    col_map = {
        "ctin": "Supplier GSTIN",
        "supplier_name": "Supplier Name",
        "cfs": "GSTR-1 Status",
        "fldtr1": "GSTR-1 Filed Date",
        "flprdr1": "GSTR-1 Period",
        "cfs3b": "GSTR-3B Status",
        "inum": "Invoice Number",
        "idt": "Invoice Date",
        "val": "Invoice Value",
        "inv_typ": "Invoice Type",
        "pos": "Place of Supply",
        "rchrg": "Reverse Charge",
        "chksum": "Checksum",
        "irn": "IRN",
        "irngendate": "IRN Date",
        "srctyp": "Source",
        # Item Level
        "rt": "Rate",
        "txval": "Taxable",
        "iamt": "IGST",
        "camt": "CGST",
        "samt": "SGST",
        "csamt": "Cess"
    }

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        has_data = False
        for section, records in all_data.items():
            if records:
                has_data = True
                # Normalize JSON data
                df = pd.DataFrame(records)
                
                # Rename columns
                df.rename(columns=col_map, inplace=True)
                
                # Requested sequence to be at the front
                priority_cols = ["Supplier Name", "Rate", "Taxable", "IGST", "CGST", "SGST", "Cess"]
                
                # Ensure all priority columns exist (fill with empty if missing)
                for col in priority_cols:
                    if col not in df.columns:
                        df[col] = ""
                
                # Get all other columns that were not in the priority list
                other_cols = [c for c in df.columns if c not in priority_cols]
                
                # Combine: Priority Columns + Remaining Original Columns
                final_cols = priority_cols + other_cols
                df = df[final_cols]
                
                # Truncate sheet name to 31 chars (Excel limit)
                sheet_name = f"{section.upper()}_Data"
                
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                print(f"  -> Added sheet: {sheet_name} ({len(records)} records)")
            else:
                print(f"  -> No data for section: {section}")
        
        if not has_data:
            print("No data found for any section! Creating empty file.")
            pd.DataFrame({"Message": ["No Data Found"]}).to_excel(writer, sheet_name="Summary")

    print("Done.")

def main():
    print("=== Sandbox GSTR-2A Downloader ===")
    
    # Hardcoded Inputs
    api_key = "key_live_ecd284949535456182df44fc9ac57ab0"
    api_secret = "secret_live_d0865b672c834093bdb0dbede371c0e3"
    # gstin = "27AAEFO0142R1Z0"
    gstin = "27AAGCE3732N1ZC"
    # username = "ULHAS_7866"
    username = "dfc6fca5ba"
    fy = "2025-26" # Updated as per user request
    
    # print(f"Using API Key: {api_key}") # Security risk to print? Maybe just say using hardcoded.
    print("Using hardcoded credentials for 27AAGCE3732N1ZC...")
    
    # 1. Platform Auth
    token = get_platform_token(api_key, api_secret)
    if not token:
        print("Exiting due to auth failure.")
        return

    # 2. GST Request OTP
    txn = request_gst_otp(token, api_key, gstin, username)
    if not txn:
        # Sometimes requests fail if already logged in? 
        # But usually we need to re-login for a fresh session if we don't have one.
        # Use input to proceed?
        retry = input("OTP Request failed or no Transaction ID. Retry manually? (y/n): ")
        if retry.lower() != 'y':
            return
    
    # 3. Verify OTP
    otp = input("Enter OTP received on registered mobile/email: ").strip()
    verify_resp = verify_gst_otp(token, api_key, gstin, username, otp)
    if not verify_resp:
        print("Exiting due to OTP failure.")
        return

    # 4. Fetch Data
    # IMPORTANT: Use the Taxpayer Token from verify_resp, NOT the Platform Token
    taxpayer_token = None
    if verify_resp:
        # Check standard paths for token
        if "data" in verify_resp:
             taxpayer_token = verify_resp["data"].get("auth_token") or verify_resp["data"].get("access_token")
        
        # Fallback to top level
        if not taxpayer_token:
             taxpayer_token = verify_resp.get("auth_token") or verify_resp.get("access_token")
            
    if not taxpayer_token:
        print(" [!] Could not extract Taxpayer Token. Verify Response structure might differ.")
        print(f"Response Keys: {verify_resp.keys() if verify_resp else 'None'}")
        if verify_resp: 
             print(f"Full Response: {verify_resp}")
        return

    print("Taxpayer Token obtained. Fetching data...")
    data = fetch_gstr2a_data(taxpayer_token, api_key, gstin, fy)
    
    # NEW: Enrich with Supplier Names
    # 1. Collect all GSTINs
    all_ctins = []
    for section, records in data.items():
        for record in records:
            if "ctin" in record:
                all_ctins.append(record["ctin"])
    
    # 2. Fetch Names (using Platform Token 'token')
    if all_ctins:
        gstin_map = fetch_supplier_names(all_ctins, token, api_key)
        
        # 3. Map back to data
        print("Mapping names to records...")
        for section, records in data.items():
            for record in records:
                if "ctin" in record:
                    # Enrich record
                    record["supplier_name"] = gstin_map.get(record["ctin"], "")
    
    # 5. Save
    process_and_save_excel(data, f"GSTR2A_{gstin}_{fy}.xlsx")

if __name__ == "__main__":
    main()
