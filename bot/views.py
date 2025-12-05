from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.conf import settings
import os

from .models import Lead, ContactQuery


@api_view(['POST'])
def save_lead(request):
    """
    Saves lead directly into Supabase PostgreSQL using Django ORM.
    """
    name = request.data.get('name')
    email = request.data.get('email')
    phone = request.data.get('phone')

    if not all([name, email, phone]):
        return Response(
            {"error": "Missing required fields"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        Lead.objects.create(
            name=name,
            email=email,
            phone=phone
        )

        return Response(
            {"message": "Lead saved successfully"},
            status=status.HTTP_201_CREATED
        )

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def send_query(request):
    """
    Stores contact query in Supabase DB and sends email.
    """
    name = request.data.get('name')
    email = request.data.get('email')
    phone = request.data.get('phone')
    query = request.data.get('query')

    if not all([name, email, phone, query]):
        return Response(
            {"error": "Missing required fields"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Save to DB
        ContactQuery.objects.create(
            name=name,
            email=email,
            phone=phone,
            query=query
        )

        # Email setup
        subject = f"New Bot Query from {name}"
        message = (
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Phone: {phone}\n\n"
            f"Query:\n{query}"
        )

        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [os.getenv("TARGET_EMAIL")],
            fail_silently=False,
        )

        return Response(
            {"message": "Query saved and email sent"},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        return Response(
            {"error": "Failed to process request", 
             "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
