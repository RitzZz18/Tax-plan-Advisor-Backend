import pdfplumber
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

print("=== GSTR-1 EXTRACTION ===")
with pdfplumber.open('media/uploads/GSTR1_27AAMCR5575Q1ZA_092025.pdf') as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables()
    main_table = max(tables, key=lambda t: len(t) if t else 0)
    
    print(f"Rows: {len(main_table)}")
    print("Looking for 'Total' row with 103 records...")
    
    for i, row in enumerate(main_table):
        row_str = str(row)
        if 'total' in row_str.lower() and '103' in row_str:
            print(f"\nFound at row {i}: {row}")

print("\n=== GSTR-3B EXTRACTION ===")
with pdfplumber.open('media/uploads/GSTR3B_27AAMCR5575Q1ZA_092025.pdf') as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables()
    
    print(f"Found {len(tables)} tables")
    for ti, table in enumerate(tables):
        if len(table) > 3:
            print(f"\nTable {ti+1} ({len(table)} rows):")
            for row in table[:3]:
                print(f"  {row}")
