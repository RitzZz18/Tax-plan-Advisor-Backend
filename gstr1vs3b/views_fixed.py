from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.conf import settings
import requests
from datetime import datetime, timedelta
from .models import GSTSession

@api_view(['POST'])
@permission_classes([AllowAny])
def generate_otp(request):
    username = request.data.get('username')
    gstin = request.data.get('gstin')
    
    if not username or not username.strip():
        return Response({'error': 'Username cannot be empty'}, status=400)
    
    if not gstin or len(gstin) != 15:
        return Response({'error': 'GSTIN must be 15 characters'}, status=400)
    
    try:
        auth_response = requests.post(
            "https://api.sandbox.co.in/authenticate",
            headers={
                "x-api-key": settings.SANDBOX_API_KEY,
                "x-api-secret": settings.SANDBOX_API_SECRET
            },
            timeout=20
        )
        
        if auth_response.status_code != 200:
            return Response({'error': 'Authentication failed'}, status=500)
        
        access_token = auth_response.json().get("data", {}).get("access_token")
        if not access_token:
            return Response({'error': 'Failed to generate token'}, status=500)
        
        otp_response = requests.post(
            "https://api.sandbox.co.in/gst/compliance/tax-payer/otp",
            json={"username": username, "gstin": gstin},
            headers={
                "x-source": "primary",
                "x-api-version": "1.0.0",
                "Authorization": access_token,
                "x-api-key": settings.SANDBOX_API_KEY,
                "Content-Type": "application/json"
            },
            timeout=20
        )
        
        if otp_response.status_code != 200:
            return Response({'error': 'OTP request failed'}, status=400)
        
        data = otp_response.json().get("data", {})
        if data.get("status_cd") == "0":
            error_code = data.get("error", {}).get("error_cd", "")
            error_msg = "OTP generation failed"
            
            if error_code == "AUTH4037":
                error_msg = "API access not enabled on GST Portal"
            elif error_code == "AUTH403":
                error_msg = "Maximum session limit exceeded"
            elif error_code == "TEC4001":
                error_msg = "OTP server is down"
            
            return Response({'error': error_msg, 'error_code': error_code}, status=400)
        
        gst_session = GSTSession.objects.create(
            username=username, gstin=gstin, access_token=access_token
        )
        
        GSTSession.objects.filter(created_at__lt=datetime.now() - timedelta(hours=24)).delete()
        
        return Response({'message': 'OTP sent successfully', 'session_id': str(gst_session.session_id)})
    
    except requests.Timeout:
        return Response({'error': 'GST API timeout. Please try again'}, status=504)
    except requests.RequestException:
        return Response({'error': 'GST API connection failed'}, status=503)
    except Exception:
        return Response({'error': 'Internal server error'}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    otp = request.data.get('otp')
    session_id = request.data.get('session_id')
    
    if not otp or not otp.strip():
        return Response({'error': 'OTP cannot be empty'}, status=400)
    
    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)
    
    try:
        gst_session = GSTSession.objects.get(session_id=session_id)
    except GSTSession.DoesNotExist:
        return Response({'error': 'Session expired. Please generate OTP again'}, status=400)
    
    try:
        verify_response = requests.post(
            "https://api.sandbox.co.in/gst/compliance/tax-payer/otp/verify",
            json={"username": gst_session.username, "gstin": gst_session.gstin},
            params={"otp": otp},
            headers={
                "x-source": "primary",
                "x-api-version": "1.0.0",
                "Authorization": gst_session.access_token,
                "x-api-key": settings.SANDBOX_API_KEY,
                "Content-Type": "application/json"
            },
            timeout=20
        )
        
        data = verify_response.json().get("data", {})
        taxpayer_token = data.get("access_token")
        
        if data.get("status_cd") == "0" or not taxpayer_token:
            return Response({'error': 'OTP verification failed'}, status=400)
        
        gst_session.taxpayer_token = taxpayer_token
        gst_session.save(update_fields=['taxpayer_token', 'updated_at'])
        
        return Response({'message': 'OTP verified successfully'})
    
    except requests.Timeout:
        return Response({'error': 'GST API timeout. Please try again'}, status=504)
    except requests.RequestException:
        return Response({'error': 'GST API connection failed'}, status=503)
    except Exception:
        return Response({'error': 'Internal server error'}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def reconcile(request):
    fy_year = request.data.get('fy_year')
    session_id = request.data.get('session_id')
    
    if not fy_year or not str(fy_year).isdigit():
        return Response({'error': 'Invalid year'}, status=400)
    
    if not session_id:
        return Response({'error': 'Session ID required'}, status=400)
    
    try:
        gst_session = GSTSession.objects.get(session_id=session_id)
        if not gst_session.taxpayer_token:
            return Response({'error': 'Please verify OTP first'}, status=400)
    except GSTSession.DoesNotExist:
        return Response({'error': 'Session expired. Please generate OTP again'}, status=400)
    
    start_year = int(fy_year)
    end_year = start_year + 1
    all_months = [(start_year, m) for m in range(4, 13)] + [(end_year, m) for m in range(1, 4)]
    current = datetime.now()
    cutoff_month = current.month - 1 if current.day < 20 else current.month
    months = [(y, m) for y, m in all_months if (y < current.year) or (y == current.year and m < cutoff_month)]
    
    if not months:
        return Response({'error': 'No valid months available'}, status=400)
    
    results = []
    for year, month in months:
        result = reconcile_month(year, month, gst_session.taxpayer_token)
        if result:
            result['year'] = year
            result['month'] = month
            results.append(result)
    
    from .models import ReconciliationReport
    ReconciliationReport.objects.create(
        username=gst_session.username,
        gstin=gst_session.gstin,
        fy_year=start_year,
        report_data=results
    )
    
    return Response({'results': results})


def reconcile_month(year, month, taxpayer_token):
    base_url = "https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-1"
    headers = {
        "x-api-version": "1.0.0",
        "Authorization": taxpayer_token,
        "x-api-key": settings.SANDBOX_API_KEY
    }
    
    try:
        gstr1_data = {}
        for dt in ["b2b", "b2cl", "b2cs", "exp", "cdnr", "b2ba", "b2cla", "b2csa", "cdnra", "nil"]:
            try:
                r = requests.get(f"{base_url}/{dt}/{year}/{month:02d}", headers=headers, timeout=20)
                if r.status_code == 200:
                    gstr1_data[dt] = r.json().get("data", {}).get("data", {}).get(dt if dt != "nil" else "nil_supplies")
                else:
                    gstr1_data[dt] = None
            except:
                gstr1_data[dt] = None
    except:
        return None

    tx1 = ig1 = cg1 = sg1 = zr1 = ng1 = 0

    for e in gstr1_data.get("b2b") or []:
        for inv in e.get("inv", []):
            if inv.get("inv_typ") not in ["SEWP", "SEWOP"]:
                for itm in inv.get("itms", []):
                    d = itm.get("itm_det", {})
                    tx1 += float(d.get("txval", 0))
                    ig1 += float(d.get("iamt", 0))
                    cg1 += float(d.get("camt", 0))
                    sg1 += float(d.get("samt", 0))
            else:
                zr1 += float(inv.get("val", 0))

    for e in gstr1_data.get("b2cl") or []:
        for inv in e.get("inv", []):
            for itm in inv.get("itms", []):
                d = itm.get("itm_det", {})
                tx1 += float(d.get("txval", 0))
                ig1 += float(d.get("iamt", 0))
                cg1 += float(d.get("camt", 0))
                sg1 += float(d.get("samt", 0))

    for e in gstr1_data.get("b2cs") or []:
        tx1 += float(e.get("txval", 0))
        ig1 += float(e.get("iamt", 0))
        cg1 += float(e.get("camt", 0))
        sg1 += float(e.get("samt", 0))

    for e in gstr1_data.get("cdnr") or []:
        for note in e.get("nt", []):
            for itm in note.get("itms", []):
                d = itm.get("itm_det", {})
                tx1 += float(d.get("txval", 0))
                ig1 += float(d.get("iamt", 0))
                cg1 += float(d.get("camt", 0))
                sg1 += float(d.get("samt", 0))

    for e in gstr1_data.get("exp") or []:
        for inv in e.get("inv", []):
            zr1 += float(inv.get("val", 0))

    ng1 = sum(float(e.get("ngsup_amt", 0)) for e in gstr1_data.get("nil") or [])

    try:
        r = requests.get(f"https://api.sandbox.co.in/gst/compliance/tax-payer/gstrs/gstr-3b/{year}/{month:02d}", headers=headers, timeout=20)
        sup = r.json().get("data", {}).get("data", {}).get("sup_details", {})
    except:
        return None

    od = sup.get("osup_det", {})
    tx3 = float(od.get("txval", 0))
    ig3 = float(od.get("iamt", 0))
    cg3 = float(od.get("camt", 0))
    sg3 = float(od.get("samt", 0))
    zr3 = float(sup.get("osup_zero", {}).get("txval", 0))
    ng3 = float(sup.get("osup_nongst", {}).get("txval", 0))

    return {"tx1": tx1, "ig1": ig1, "cg1": cg1, "sg1": sg1, "zr1": zr1, "ng1": ng1,
            "tx3": tx3, "ig3": ig3, "cg3": cg3, "sg3": sg3, "zr3": zr3, "ng3": ng3}
