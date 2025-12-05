from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.conf import settings
import os
from .supabase_client import supabase

@api_view(['POST'])
def save_lead(request):
    """
    Manually extracts data and saves to Supabase 'leads' table.
    """
    # 1. Extract data manually
    name = request.data.get('name')
    email = request.data.get('email')
    phone = request.data.get('phone')

    # 2. Simple Validation (Check if fields exist)
    if not all([name, email, phone]):
        return Response(
            {"error": "Missing required fields: name, email, or phone"}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    # 3. Insert into Supabase
    try:
        data = {
            "name": name,
            "email": email,
            "phone": phone
        }
        # Execute insert
        supabase.table('leads').insert(data).execute()
        return Response({"message": "Lead saved successfully"}, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def send_query(request):
    """
    Manually extracts data, saves to Supabase 'contact_queries', and sends email.
    """
    # 1. Extract data manually
    name = request.data.get('name')
    email = request.data.get('email')
    phone = request.data.get('phone')
    query = request.data.get('query')

    # 2. Validation
    if not all([name, email, phone, query]):
        return Response(
            {"error": "Missing required fields."}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # 3. Insert into Supabase
        data = {
            "name": name,
            "email": email,
            "phone": phone,
            "query": query
        }
        supabase.table('contact_queries').insert(data).execute()

        # 4. Send Email
        subject = f"New Bot Query from {name}"
        message = (
            f"You have received a new query via the Chatbot.\n\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Phone: {phone}\n\n"
            f"Query:\n{query}"
        )

        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [os.getenv('TARGET_EMAIL')], 
            fail_silently=False,
        )

        return Response({"message": "Query saved and email sent"}, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"Error: {e}")
        return Response({"error": "Failed to process request", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)