"""
Django REST Framework Views for TDS API
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from django.http import HttpResponse
import pandas as pd
from datetime import date, datetime
import io

from .tds_logic import (
    TDS_SECTIONS,
    get_all_sections_data,
    get_section_by_code,
    detect_category_from_pan,
    validate_pan_format,
    get_applicable_rate,
    calculate_tds,
    calculate_due_date,
    format_indian_number
)


class TDSSectionsView(APIView):
    """Get all TDS sections reference data"""
    
    def get(self, request):
        sections = get_all_sections_data()
        return Response({
            'success': True,
            'count': len(sections),
            'sections': sections
        })


class BulkCalculateView(APIView):
    """Process bulk TDS calculations from uploaded Excel file"""
    parser_classes = [MultiPartParser]
    
    def post(self, request):
        if 'file' not in request.FILES:
            return Response(
                {'success': False, 'error': 'No file uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        
        try:
            # Read Excel file
            df = pd.read_excel(file)
            
            # Validate required columns
            required_columns = ['Deductee Name', 'Deductee PAN', 'TDS Section', 'Transaction Amount', 'Date of Deduction']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                return Response(
                    {'success': False, 'error': f'Missing required columns: {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Process each row
            results = self._process_bulk_tds(df)
            
            # Calculate summary
            total_transactions = len(results)
            taxable_count = sum(1 for r in results if r['status'] == 'Taxable')
            under_threshold_count = sum(1 for r in results if r['status'] == 'Under Threshold')
            total_tds = sum(r['tds_amount'] for r in results)
            
            return Response({
                'success': True,
                'summary': {
                    'total_transactions': total_transactions,
                    'taxable_count': taxable_count,
                    'under_threshold_count': under_threshold_count,
                    'total_tds': total_tds,
                    'total_tds_formatted': format_indian_number(total_tds)
                },
                'results': results
            })
            
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _process_bulk_tds(self, df):
        """Process bulk TDS calculations from DataFrame"""
        results = []
        
        for idx, row in df.iterrows():
            try:
                # Extract data
                deductee_name = str(row.get('Deductee Name', '')).strip()
                deductee_pan = str(row.get('Deductee PAN', '')).strip().upper()
                section_code = str(row.get('TDS Section', '')).strip()
                
                # Handle amount
                amount_val = row.get('Transaction Amount', 0)
                if pd.isna(amount_val):
                    amount = 0
                else:
                    amount = float(amount_val)
                
                # Handle date
                date_val = row.get('Date of Deduction')
                if pd.isna(date_val):
                    deduction_date = date.today()
                elif isinstance(date_val, (datetime, date)):
                    deduction_date = date_val if isinstance(date_val, date) else date_val.date()
                else:
                    try:
                        deduction_date = pd.to_datetime(date_val).date()
                    except:
                        deduction_date = date.today()
                
                # Detect category from PAN
                pan_available = bool(deductee_pan) and validate_pan_format(deductee_pan)
                category = detect_category_from_pan(deductee_pan) if pan_available else "Individual / HUF"
                category_short = "Company/Firm" if category and "Company" in category else "Individual/HUF"
                
                # Get section
                section = get_section_by_code(section_code)
                
                if not section:
                    results.append({
                        'deductee_name': deductee_name,
                        'deductee_pan': deductee_pan if deductee_pan else "Not Provided",
                        'detected_category': category_short,
                        'tds_section': section_code,
                        'transaction_amount': amount,
                        'applicable_rate': "N/A",
                        'tds_amount': 0,
                        'date_of_deduction': deduction_date.strftime('%d-%b-%Y'),
                        'due_date': "N/A",
                        'status': f"Invalid Section Code: {section_code}"
                    })
                    continue
                
                # Get applicable rate
                rate, rate_display = get_applicable_rate(section, category, pan_available)
                
                # Calculate TDS
                tds_amount, above_threshold, tds_status = calculate_tds(
                    amount, rate, section.threshold, section.tds_on_excess
                )
                
                # Calculate due date
                due_date = calculate_due_date(deduction_date, section)
                
                results.append({
                    'deductee_name': deductee_name,
                    'deductee_pan': deductee_pan if deductee_pan else "Not Provided",
                    'detected_category': category_short,
                    'tds_section': section.section,
                    'transaction_amount': amount,
                    'applicable_rate': rate_display,
                    'tds_amount': tds_amount,
                    'date_of_deduction': deduction_date.strftime('%d-%b-%Y'),
                    'due_date': due_date.strftime('%d-%b-%Y'),
                    'status': tds_status
                })
                
            except Exception as e:
                results.append({
                    'deductee_name': str(row.get('Deductee Name', '')),
                    'deductee_pan': str(row.get('Deductee PAN', '')),
                    'detected_category': "Error",
                    'tds_section': str(row.get('TDS Section', '')),
                    'transaction_amount': 0,
                    'applicable_rate': "Error",
                    'tds_amount': 0,
                    'date_of_deduction': "Error",
                    'due_date': "Error",
                    'status': f"Processing Error: {str(e)}"
                })
        
        return results


class DownloadTemplateView(APIView):
    """Download sample Excel template"""
    
    def get(self, request):
        # Create sample data
        sample_data = {
            'Deductee Name': ['ABC Corporation', 'John Doe', 'XYZ Ltd', 'No PAN Person'],
            'Deductee PAN': ['ABCPD1234E', 'BXYPJ5678K', 'XYZPF9012L', ''],
            'TDS Section': ['194C', '194J(b)', '194Q-Exceed', '194A'],
            'Transaction Amount': [150000, 75000, 600000, 50000],
            'Date of Deduction': ['2026-01-15', '2026-01-20', '2026-01-10', '2026-01-05']
        }
        
        df = pd.DataFrame(sample_data)
        
        # Create Excel file in memory
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="tds_bulk_template.xlsx"'
        
        return response


class DownloadResultsView(APIView):
    """Generate and download results as Excel"""
    
    def post(self, request):
        results = request.data.get('results', [])
        
        if not results:
            return Response(
                {'success': False, 'error': 'No results data provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        # Rename columns to display format
        column_mapping = {
            'deductee_name': 'Deductee Name',
            'deductee_pan': 'Deductee PAN',
            'detected_category': 'Detected Category',
            'tds_section': 'TDS Section',
            'transaction_amount': 'Transaction Amount',
            'applicable_rate': 'Applicable TDS Rate',
            'tds_amount': 'TDS Amount',
            'date_of_deduction': 'Date of Deduction',
            'due_date': 'Due Date for Payment',
            'status': 'Status'
        }
        df = df.rename(columns=column_mapping)
        
        # Create Excel file in memory
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="tds_calculation_results.xlsx"'
        
        return response
