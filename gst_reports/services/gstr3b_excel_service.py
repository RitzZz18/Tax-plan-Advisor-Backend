# gst_reports/services/gstr3b_excel_service.py

import io
import calendar
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from gst_reports.services.gst_data_service import GSTDataService

class GSTR3BExcelService:
    @staticmethod
    def generate(gstin, year, month, taxpayer_token, force_refresh=False):
        data = GSTDataService.get_gstr3b_filed(
            gstin=gstin, year=year, month=month, taxpayer_token=taxpayer_token, force_refresh=force_refresh
        )
        if not data:
            raise Exception("Failed to fetch GSTR-3B data")
        
        gstr3b = data
        if "data" in gstr3b and isinstance(gstr3b["data"], dict):
            gstr3b = gstr3b["data"]
            
        ret_period = gstr3b.get("ret_period", f"{month:02d}{year}")
        month_name = calendar.month_name[month]

        wb = Workbook()
        ws = wb.active
        ws.title = "GSTR-3B Summary"

        # Styles
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        section_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        section_font = Font(bold=True, size=11, color="1F4E78")
        border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        money_format = '₹#,##0.00'

        ws.merge_cells('A1:F1')
        ws['A1'] = f"GSTR-3B Details - {month_name} {year}"
        ws['A1'].font = Font(bold=True, size=16, color="1F4E78")
        ws['A1'].alignment = Alignment(horizontal='center')
        ws['A2'] = f"GSTIN: {gstin} | Return Period: {ret_period}"
        ws['A2'].font = Font(bold=True, size=11)

        row = 4
        # TABLE 3.1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        ws.cell(row, 1, "TABLE 3.1 - OUTWARD SUPPLIES").fill = section_fill
        ws.cell(row, 1).font = section_font
        row += 1
        headers = ["Particulars", "Taxable Value", "IGST", "CGST", "SGST", "CESS"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row, col, h)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
        row += 1
        sup_details = gstr3b.get("sup_details", {})
        outward_rows = [
            ("3.1(a) Outward taxable supplies", "osup_det"),
            ("3.1(b) Outward taxable supplies (zero rated)", "osup_zero"),
            ("3.1(c) Other outward supplies (Nil rated, exempted)", "osup_nil_exmp"),
            ("3.1(d) Inward supplies liable to reverse charge", "isup_rev"),
            ("3.1(e) Non-GST outward supplies", "osup_nongst"),
        ]
        for label, key in outward_rows:
            sec = sup_details.get(key, {})
            ws.cell(row, 1, label).border = border
            for c, k in enumerate(["txval", "iamt", "camt", "samt", "csamt"], 2):
                ws.cell(row, c, float(sec.get(k, 0) or 0)).number_format = money_format
                ws.cell(row, c).border = border
            row += 1
        
        row += 1
        # TABLE 4
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        ws.cell(row, 1, "TABLE 4 - ELIGIBLE ITC").fill = section_fill
        ws.cell(row, 1).font = section_font
        row += 1
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row, col, h); cell.fill = header_fill; cell.font = header_font; cell.border = border
        row += 1
        itc_elg = gstr3b.get("itc_elg", {})
        itc_type_labels = {"IMPG": "4(A)(1) Import of goods", "IMPS": "4(A)(2) Import of services", "ISRC": "4(A)(3) Inward supplies liable to RCM", "ISD": "4(A)(4) Inward supplies from ISD", "OTH": "4(A)(5) All other ITC"}
        for itc_item in itc_elg.get("itc_avl", []):
            label = itc_type_labels.get(itc_item.get("ty", ""), f"4(A) {itc_item.get('ty', '')}")
            ws.cell(row, 1, label).border = border
            ws.cell(row, 2, "-").border = border
            for c, k in enumerate(["iamt", "camt", "samt", "csamt"], 3):
                ws.cell(row, c, float(itc_item.get(k, 0) or 0)).number_format = money_format
                ws.cell(row, c).border = border
            row += 1
        
        itc_net = itc_elg.get("itc_net", {})
        ws.cell(row, 1, "4(C) Net ITC Available").font = Font(bold=True)
        ws.cell(row, 1).border = border
        ws.cell(row, 2, "-").border = border
        for c, k in enumerate(["iamt", "camt", "samt", "csamt"], 3):
            cell = ws.cell(row, c, float(itc_net.get(k, 0) or 0))
            cell.number_format = money_format; cell.border = border; cell.font = Font(bold=True)
        row += 2

        # TABLE 6
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        ws.cell(row, 1, "TABLE 6 - TAX PAYMENT").fill = section_fill; ws.cell(row, 1).font = section_font; row += 1
        pay_headers = ["Description", "IGST", "CGST", "SGST", "CESS", "Interest"]
        for col, h in enumerate(pay_headers, 1):
            cell = ws.cell(row, col, h); cell.fill = header_fill; cell.font = header_font; cell.border = border
        row += 1
        for item in gstr3b.get("tx_pmt", {}).get("net_tax_pay", []):
            ws.cell(row, 1, item.get("tran_desc", "")).border = border
            keys = [("igst", "tx"), ("cgst", "tx"), ("sgst", "tx"), ("cess", "tx"), ("igst", "intr")]
            for c, (k1, k2) in enumerate(keys, 2):
                val = item.get(k1, {}).get(k2, 0) if isinstance(item.get(k1), dict) else 0
                ws.cell(row, c, float(val or 0)).number_format = money_format
                ws.cell(row, c).border = border
            row += 1
        
        ws.column_dimensions['A'].width = 45
        for col in ['B', 'C', 'D', 'E', 'F']: ws.column_dimensions[col].width = 15
        
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        filename = f"GSTR3B_Details_{gstin}_{month_name}_{year}.xlsx"
        return output, filename
    @staticmethod
    def generate_multi(gstin, periods, taxpayer_token, force_refresh=False):
        """
        Generate a multi-sheet GSTR-3B Excel workbook for multiple periods.
        """
        wb = Workbook()
        # Remove default sheet
        default_sheet = wb.active
        wb.remove(default_sheet)

        for yr, mn in periods:
            data = GSTDataService.get_gstr3b_filed(
                gstin=gstin, year=yr, month=mn, taxpayer_token=taxpayer_token, force_refresh=force_refresh
            )
            if not data:
                continue
            
            gstr3b = data
            if "data" in gstr3b and isinstance(gstr3b["data"], dict):
                gstr3b = gstr3b["data"]
                
            month_name = calendar.month_name[mn]
            sheet_title = f"{month_name[:3]}_{yr}"
            ws = wb.create_sheet(title=sheet_title)

            # Styles (Re-used from generate method)
            header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF", size=11)
            section_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            section_font = Font(bold=True, size=11, color="1F4E78")
            border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            money_format = '₹#,##0.00'

            ws.merge_cells('A1:F1')
            ws['A1'] = f"GSTR-3B Details - {month_name} {yr}"
            ws['A1'].font = Font(bold=True, size=16, color="1F4E78")
            ws['A1'].alignment = Alignment(horizontal='center')
            ws['A2'] = f"GSTIN: {gstin} | Return Period: {gstr3b.get('ret_period', '')}"
            ws['A2'].font = Font(bold=True, size=11)

            row_idx = 4
            # TABLE 3.1
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=6)
            ws.cell(row_idx, 1, "TABLE 3.1 - OUTWARD SUPPLIES").fill = section_fill
            ws.cell(row_idx, 1).font = section_font
            row_idx += 1
            headers = ["Particulars", "Taxable Value", "IGST", "CGST", "SGST", "CESS"]
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row_idx, col, h)
                cell.fill = header_fill; cell.font = header_font; cell.border = border
            row_idx += 1
            sup_details = gstr3b.get("sup_details", {})
            outward_rows = [
                ("3.1(a) Outward taxable supplies", "osup_det"),
                ("3.1(b) Outward taxable supplies (zero rated)", "osup_zero"),
                ("3.1(c) Other outward supplies (Nil rated, exempted)", "osup_nil_exmp"),
                ("3.1(d) Inward supplies liable to reverse charge", "isup_rev"),
                ("3.1(e) Non-GST outward supplies", "osup_nongst"),
            ]
            for label, key in outward_rows:
                sec = sup_details.get(key, {})
                ws.cell(row_idx, 1, label).border = border
                for c, k in enumerate(["txval", "iamt", "camt", "samt", "csamt"], 2):
                    ws.cell(row_idx, c, float(sec.get(k, 0) or 0)).number_format = money_format
                    ws.cell(row_idx, c).border = border
                row_idx += 1
            
            row_idx += 1
            # TABLE 4
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=6)
            ws.cell(row_idx, 1, "TABLE 4 - ELIGIBLE ITC").fill = section_fill
            ws.cell(row_idx, 1).font = section_font
            row_idx += 1
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row_idx, col, h); cell.fill = header_fill; cell.font = header_font; cell.border = border
            row_idx += 1
            itc_elg = gstr3b.get("itc_elg", {})
            itc_type_labels = {"IMPG": "4(A)(1) Import of goods", "IMPS": "4(A)(2) Import of services", "ISRC": "4(A)(3) Inward supplies liable to RCM", "ISD": "4(A)(4) Inward supplies from ISD", "OTH": "4(A)(5) All other ITC"}
            for itc_item in itc_elg.get("itc_avl", []):
                label = itc_type_labels.get(itc_item.get("ty", ""), f"4(A) {itc_item.get('ty', '')}")
                ws.cell(row_idx, 1, label).border = border
                ws.cell(row_idx, 2, "-").border = border
                for c, k in enumerate(["iamt", "camt", "samt", "csamt"], 3):
                    ws.cell(row_idx, c, float(itc_item.get(k, 0) or 0)).number_format = money_format
                    ws.cell(row_idx, c).border = border
                row_idx += 1
            
            itc_net = itc_elg.get("itc_net", {})
            ws.cell(row_idx, 1, "4(C) Net ITC Available").font = Font(bold=True)
            ws.cell(row_idx, 1).border = border
            ws.cell(row_idx, 2, "-").border = border
            for c, k in enumerate(["iamt", "camt", "samt", "csamt"], 3):
                cell = ws.cell(row_idx, c, float(itc_net.get(k, 0) or 0))
                cell.number_format = money_format; cell.border = border; cell.font = Font(bold=True)
            row_idx += 2

            # TABLE 6
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=6)
            ws.cell(row_idx, 1, "TABLE 6 - TAX PAYMENT").fill = section_fill; ws.cell(row_idx, 1).font = section_font; row_idx += 1
            pay_headers = ["Description", "IGST", "CGST", "SGST", "CESS", "Interest"]
            for col, h in enumerate(pay_headers, 1):
                cell = ws.cell(row_idx, col, h); cell.fill = header_fill; cell.font = header_font; cell.border = border
            row_idx += 1
            for item in gstr3b.get("tx_pmt", {}).get("net_tax_pay", []):
                ws.cell(row_idx, 1, item.get("tran_desc", "")).border = border
                keys = [("igst", "tx"), ("cgst", "tx"), ("sgst", "tx"), ("cess", "tx"), ("igst", "intr")]
                for c, (k1, k2) in enumerate(keys, 2):
                    val = item.get(k1, {}).get(k2, 0) if isinstance(item.get(k1), dict) else 0
                    ws.cell(row_idx, c, float(val or 0)).number_format = money_format
                    ws.cell(row_idx, c).border = border
                row_idx += 1
            
            ws.column_dimensions['A'].width = 45
            for col in ['B', 'C', 'D', 'E', 'F']: ws.column_dimensions[col].width = 15

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        filename = f"GSTR3B_Details_Multi_{gstin}.xlsx"
        return output, filename
