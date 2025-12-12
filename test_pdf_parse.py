import pdfplumber
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Test GSTR-1
print("=== GSTR-1 ===")
with pdfplumber.open('media/uploads/GSTR1_27AAMCR5575Q1ZA_092025.pdf') as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables()
    print(f"Found {len(tables)} tables on page 1")
    
    # Look for the main data table (usually the largest one)
    for i, table in enumerate(tables):
        print(f"\nTable {i+1}: {len(table)} rows x {len(table[0]) if table else 0} cols")
        if len(table) > 5:  # Main data table
            print("Headers:", table[0][:5])
            for row in table[1:4]:  # First 3 data rows
                print("Row:", row[:5])

print("\n\n=== GSTR-3B ===")
with pdfplumber.open('media/uploads/GSTR3B_27AAMCR5575Q1ZA_092025.pdf') as pdf:
    page = pdf.pages[0]
    tables = page.extract_tables()
    print(f"Found {len(tables)} tables on page 1")
    
    for i, table in enumerate(tables):
        print(f"\nTable {i+1}: {len(table)} rows x {len(table[0]) if table else 0} cols")
        if len(table) > 2:
            print("Headers:", table[0][:5])
            for row in table[1:3]:
                print("Row:", row[:5])
