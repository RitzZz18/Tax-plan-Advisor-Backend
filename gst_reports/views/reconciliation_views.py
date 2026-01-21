# gst_reports/views/reconciliation_views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from datetime import date, timedelta
import pandas as pd

from gst_reports.services.gst_data_service import GSTDataService
from gst_reports.utils import get_valid_session
from gst_reports.services.gstr1_vs_3b_service import reconcile_gstr1_vs_3b, reconcile_comprehensive
from gst_reports.services.gstr1_vs_books_service import GSTR1BooksReconciliationService
from gst_reports.services.gstr3b_vs_books_service import GSTR3BBooksReconciliationService
from gst_reports.services.gstr2b_vs_books_service import GSTR2BBooksReconciliationService
from gst_reports.models import GSTReport

@api_view(["POST"])
@permission_classes([AllowAny])
def reconcile_1_vs_3b(request):
    """
    Unified GSTR-1 vs GSTR-3B Reconciliation endpoint.
    """
    try:
        fy_year = int(request.data.get("fy_year"))
        session_id = request.data.get("session_id")
        period_type = request.data.get("period_type", "fy")  
        period_value = request.data.get("period_value")  
        force_refresh = request.data.get("force_refresh", False)

        if not session_id:
            return Response({"error": "Session ID required"}, status=400)

        session, error = get_valid_session(session_id)
        if error:
            return Response({"error": error}, status=401)

        # Date Cutoff Logic
        today = date.today()
        if today.day <= 10:
            cutoff_date = (today.replace(day=1) - timedelta(days=45))
        else:
            cutoff_date = (today.replace(day=1) - timedelta(days=15))
        
        cutoff_y, cutoff_m = cutoff_date.year, cutoff_date.month

        # Generate months list
        months_to_fetch = []
        if period_type == "fy":
            for m in range(4, 13): months_to_fetch.append((fy_year, m))
            for m in range(1, 4): months_to_fetch.append((fy_year + 1, m))
        elif period_type == "quarter":
            q = int(period_value)
            months_to_fetch = [(fy_year if m >= 4 else fy_year + 1, m) for m in ([4,5,6] if q==1 else [7,8,9] if q==2 else [10,11,12] if q==3 else [1,2,3])]
        elif period_type == "month":
            m = int(period_value)
            months_to_fetch = [(fy_year if m >= 4 else fy_year + 1, m)]

        final_data = []
        for y, m in months_to_fetch:
            if y > cutoff_y or (y == cutoff_y and m > cutoff_m):
                continue
                
            res = reconcile_gstr1_vs_3b(y, m, session.gstin, session.taxpayer_token, force_refresh)
            if res:
                final_data.append(res)

        # Save report if needed (Optional: current frontend might not use DB records for this yet)
        GSTReport.objects.create(
            report_type='GSTR1_VS_3B',
            username=session.username,
            gstin=session.gstin,
            year=fy_year,
            reco_type=period_type.upper(),
            report_data=final_data
        )

        return Response({
            "status": "success",
            "gstin": session.gstin,
            "data": final_data
        })
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def reconcile_1_vs_books(request):
    """
    Unified GSTR-1 vs Books Reconciliation endpoint.
    """
    session_id = request.data.get('session_id')
    reco_type = request.data.get('reco_type') # MONTHLY, QUARTERLY, FY
    year = request.data.get('year')
    month = request.data.get('month')
    quarter = request.data.get('quarter')
    force_refresh = request.data.get('force_refresh', False)

    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)

    session, error = get_valid_session(session_id)
    if error:
        return Response({'error': error}, status=401)

    if 'file' not in request.FILES:
        return Response({'error': 'No file uploaded'}, status=400)

    try:
        file_bytes = request.FILES['file'].read()
        service = GSTR1BooksReconciliationService(taxpayer_token=session.taxpayer_token)
        results = service.run(
            file_bytes=file_bytes,
            reco_type=reco_type,
            year=int(year),
            month=int(month) if month else None,
            quarter=quarter,
            business_gstin=session.gstin,
            force_refresh=force_refresh
        )

        # Transform DataFrames to dict for JSON response
        json_results = {}
        for k, v in results.items():
            if isinstance(v, pd.DataFrame):
                json_results[k] = v.to_dict(orient='records')
            else:
                json_results[k] = v

        # Save report
        GSTReport.objects.create(
            report_type='GSTR1_VS_BOOK',
            username=session.username,
            gstin=session.gstin,
            year=int(year),
            month=int(month) if month else None,
            quarter=quarter,
            reco_type=reco_type,
            report_data=json_results
        )

        return Response({
            'status': 'success',
            'data': json_results,
            'summary': json_results.get('summary'),
            'session_info': {
                'party_name': session.username, # Or fetch legal name if available
                'gstin': session.gstin,
                'year': year,
                'month': month,
                'quarter': quarter,
                'reco_type': reco_type
            }
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def reconcile_3b_vs_books(request):
    """
    Unified GSTR-3B vs Books Reconciliation endpoint.
    """
    session_id = request.data.get('session_id')
    reco_type = request.data.get('reco_type')
    year = request.data.get('year')
    month = request.data.get('month')
    quarter = request.data.get('quarter')
    force_refresh = request.data.get('force_refresh', False)

    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)

    session, error = get_valid_session(session_id)
    if error:
        return Response({'error': error}, status=401)

    if 'file' not in request.FILES:
        return Response({'error': 'No file uploaded'}, status=400)

    try:
        df = pd.read_excel(request.FILES['file'])
        service = GSTR3BBooksReconciliationService(taxpayer_token=session.taxpayer_token)
        
        final_report = service.run(
            df=df,
            reco_type=reco_type,
            year=int(year),
            gstin=session.gstin,
            month=int(month) if month else None,
            quarter=quarter,
            force_refresh=force_refresh
        )

        # Save report
        GSTReport.objects.create(
            report_type='GSTR3B_VS_BOOK',
            username=session.username,
            gstin=session.gstin,
            year=int(year),
            month=int(month) if month else None,
            quarter=quarter,
            reco_type=reco_type,
            report_data=final_report
        )

        return Response({
            'status': 'success',
            'data': final_report,
            'session_info': {
                'party_name': session.username,
                'gstin': session.gstin,
                'year': year,
                'month': month,
                'quarter': quarter,
                'reco_type': reco_type
            }
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)
@api_view(['POST'])
@permission_classes([AllowAny])
def reconcile_2b_vs_books(request):
    """
    Unified GSTR-2B vs Books Reconciliation endpoint.
    """
    session_id = request.data.get('session_id')
    reco_type = request.data.get('period_type', 'Monthly')
    fy_year = request.data.get('fy_year')
    month = request.data.get('period_value') # For Monthly
    quarter = request.data.get('period_value') # For Quarterly
    tolerance = float(request.data.get('tolerance', 1.0))
    force_refresh = request.data.get('force_refresh', False)

    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)

    session, error = get_valid_session(session_id)
    if error:
        return Response({'error': error}, status=401)

    if 'file' not in request.FILES:
        return Response({'error': 'No books file uploaded'}, status=400)

    try:
        books_df = pd.read_excel(request.FILES['file'])
        service = GSTR2BBooksReconciliationService(taxpayer_token=session.taxpayer_token)
        
        result = service.run(
            books_df=books_df,
            reco_type=reco_type,
            year=int(fy_year),
            gstin=session.gstin,
            month_name=month if reco_type == 'Monthly' else None,
            quarter_name=quarter if reco_type == 'Quarterly' else None,
            tolerance=tolerance,
            force_refresh=force_refresh
        )

        GSTReport.objects.create(
            report_type='GSTR2B_VS_BOOK',
            username=session.username,
            gstin=session.gstin,
            year=int(fy_year),
            reco_type=reco_type.upper(),
            report_data=result
        )

        response_data = result # Assign result to response_data
        return Response({
            'status': 'success',
            'data': response_data,
            'session_info': {
                'party_name': session.username,
                'gstin': session.gstin,
                'year': fy_year,
                'month': month,
                'quarter': quarter,
                'reco_type': reco_type
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=500)

@api_view(["POST"])
@permission_classes([AllowAny])
def reconcile_comprehensive_view(request):
    """
    Unified GSTR-1 vs GSTR-3B vs GSTR-2B Comprehensive Reconciliation endpoint.
    """
    try:
        fy_year = int(request.data.get("fy_year"))
        session_id = request.data.get("session_id")
        period_type = request.data.get("period_type", "fy")  
        period_value = request.data.get("period_value")  
        force_refresh = request.data.get("force_refresh", False)

        if not session_id:
            return Response({"error": "Session ID required"}, status=400)

        session, error = get_valid_session(session_id)
        if error:
            return Response({"error": error}, status=401)

        # Generate months list
        months_to_fetch = []
        if period_type == "fy":
            for m in range(4, 13): months_to_fetch.append((fy_year, m))
            for m in range(1, 4): months_to_fetch.append((fy_year + 1, m))
        elif period_type == "quarter":
            q = int(period_value)
            months_to_fetch = [(fy_year if m >= 4 else fy_year + 1, m) for m in ([4,5,6] if q==1 else [7,8,9] if q==2 else [10,11,12] if q==3 else [1,2,3])]
        elif period_type == "month":
            m = int(period_value)
            months_to_fetch = [(fy_year if m >= 4 else fy_year + 1, m)]

        final_data = []
        for y, m in months_to_fetch:
            res = reconcile_comprehensive(y, m, session.gstin, session.taxpayer_token, force_refresh)
            if res:
                final_data.append(res)

        GSTReport.objects.create(
            report_type='GSTR1_3B_2B_COMPREHENSIVE',
            username=session.username,
            gstin=session.gstin,
            year=fy_year,
            reco_type=period_type.upper(),
            report_data=final_data
        )

        return Response({
            "status": "success",
            "gstin": session.gstin,
            "data": final_data,
            "session_info": {
                "party_name": session.username,
                "gstin": session.gstin,
                "year": fy_year,
                "period_type": period_type,
                "period_value": period_value
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e)}, status=500)
