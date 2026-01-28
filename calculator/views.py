from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from datetime import datetime

from .tds_logic import get_all_sections_list, calculate_full_tds, detect_category_from_pan, validate_pan_format
from .serializers import CalculateRequestSerializer, ExcelRequestSerializer
from .excel_generator import generate_excel_report, get_excel_filename


@api_view(['GET'])
def get_sections(request):
    """Get all TDS sections for dropdown"""
    sections = get_all_sections_list()
    return Response(sections)


@api_view(['POST'])
def calculate_tds(request):
    """Calculate TDS for one or more transactions"""
    serializer = CalculateRequestSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    deductor = data['deductor']
    transactions = data['transactions']
    
    results = []
    for idx, txn in enumerate(transactions, 1):
        # Convert date strings to date objects if needed
        deduction_date = txn['deduction_date']
        payment_date = txn['payment_date']
        
        if isinstance(deduction_date, str):
            deduction_date = datetime.strptime(deduction_date, '%Y-%m-%d').date()
        if isinstance(payment_date, str):
            payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
        
        # Get deductee details
        deductee_name = txn.get('deductee_name', '')
        deductee_pan = txn.get('deductee_pan', '')
        no_pan_available = txn.get('no_pan_available', False)
        
        # Determine category - auto-detect from PAN if available
        if not no_pan_available and deductee_pan:
            detected_category = detect_category_from_pan(deductee_pan)
            category = detected_category if detected_category else txn['category']
            pan_available = True
        else:
            category = txn['category']
            pan_available = False
        
        result = calculate_full_tds(
            section_code=txn['section_code'],
            amount=txn['amount'],
            category=category,
            pan_available=pan_available,
            deduction_date=deduction_date,
            payment_date=payment_date,
            threshold_type=txn.get('threshold_type'),
            annual_threshold_exceeded=txn.get('annual_threshold_exceeded', False),
            selected_slab=txn.get('selected_slab'),
            selected_condition=txn.get('selected_condition'),
            threshold_exceeded_before=txn.get('threshold_exceeded_before', False)
        )
        
        # Add deductee info to result
        result['transaction_number'] = idx
        result['deductee_name'] = deductee_name
        result['deductee_pan'] = deductee_pan if not no_pan_available else 'N/A'
        result['no_pan_available'] = no_pan_available
        result['detected_category'] = category
        
        results.append(result)
    
    return Response({
        'deductor': {
            'deductor_name': deductor['deductor_name'],
            'tan_number': deductor['tan_number']
        },
        'results': results
    })


@api_view(['POST'])
def generate_excel(request):
    """Generate Excel report for TDS calculations"""
    serializer = ExcelRequestSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    deductor = data['deductor']
    results = data['results']
    
    # Generate Excel file
    excel_file = generate_excel_report(
        entity_name=deductor['deductor_name'],
        pan_number=deductor['tan_number'],
        results=results
    )
    
    # Generate filename (uses entity name)
    filename = get_excel_filename(entity_name=deductor.get('entity_name', 'TDS_Report'))
    
    # Return as downloadable file
    response = HttpResponse(
        excel_file.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response
