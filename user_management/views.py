from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema # Import for docs
from drf_yasg import openapi

from .models import UserProfile, ConsultantClientLink
from .serializers import (
    LoginSerializer, 
    ConsultantSignupSerializer, 
    CreateClientSerializer,
    UserProfileSerializer,
    ClientDashboardSerializer
)

# --- Permissions ---
class IsConsultant(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.profile.is_consultant

class IsClient(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.profile.is_client


# --- Auth Views ---

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        request_body=LoginSerializer,
        responses={
            200: openapi.Response(
                description="Successful Login",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'token': openapi.Schema(type=openapi.TYPE_STRING, description='Auth Token'),
                        'role': openapi.Schema(type=openapi.TYPE_STRING, description='User Role (CONSULTANT/CLIENT)'),
                        'username': openapi.Schema(type=openapi.TYPE_STRING),
                        'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    }
                )
            ),
            400: "Invalid Credentials"
        }
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data
        token, created = Token.objects.get_or_create(user=user)
        
        return Response({
            "token": token.key,
            "role": user.profile.role,
            "username": user.username,
            "user_id": user.id
        })

class ConsultantSignupView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ConsultantSignupSerializer
    # Generic views document themselves automatically!


# --- Consultant Dashboard Views ---

class ConsultantClientListView(generics.ListCreateAPIView):
    """
    GET: List all clients managed by this consultant.
    POST: Create a new client and link to this consultant.
    """
    permission_classes = [IsConsultant]
    serializer_class = ClientDashboardSerializer # Usage for GET is implicit, override for POST if needed

    def get_queryset(self):
        linked_clients = ConsultantClientLink.objects.filter(consultant=self.request.user.profile)
        client_profiles = [link.client for link in linked_clients]
        return client_profiles 

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = ClientDashboardSerializer(queryset, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        request_body=CreateClientSerializer,
        responses={201: "Client Created Successfully"}
    )
    def post(self, request):
        serializer = CreateClientSerializer(data=request.data)
        if serializer.is_valid():
            new_client_user = serializer.save()
            ConsultantClientLink.objects.create(
                consultant=request.user.profile,
                client=new_client_user.profile
            )
            return Response({"message": "Client created successfully", "client_id": new_client_user.profile.id}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConsultantClientDetailView(APIView):
    """
    View specific client's details.
    """
    permission_classes = [IsConsultant]
    
    @swagger_auto_schema(
        responses={
            200: openapi.Response(
            description="Client Details & Stats",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'client_info': openapi.Schema(type=openapi.TYPE_OBJECT, description="Client Profile Data"),
                    'stats': openapi.Schema(
                        type=openapi.TYPE_OBJECT, 
                        properties={
                            'pending_tasks': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'investments_value': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'last_login': openapi.Schema(type=openapi.TYPE_STRING, format='date-time'),
                        }
                    ),
                }
            ))
        }
    )
    def get(self, request, client_id):
        consultant_profile = request.user.profile
        link = get_object_or_404(ConsultantClientLink, consultant=consultant_profile, client_id=client_id)
        client_profile = link.client
        
        data = {
            "client_info": ClientDashboardSerializer(client_profile).data,
            "stats": {
                "pending_tasks": 5,
                "investments_value": 1200000,
                "last_login": client_profile.user.last_login
            }
        }
        return Response(data)

# --- Client Dashboard Views ---

class ClientDashboardView(APIView):
    """
    View own dashboard data.
    """
    permission_classes = [IsClient]
    
    @swagger_auto_schema(
        responses={
            200: openapi.Response(
                description="Client Dashboard Data",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'welcome_message': openapi.Schema(type=openapi.TYPE_STRING),
                        'profile': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'reports': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
                    }
                )
            )
        }
    )
    def get(self, request):
        client_profile = request.user.profile
        
        data = {
            "welcome_message": f"Welcome back, {client_profile.user.first_name}",
            "profile": UserProfileSerializer(client_profile).data,
            "reports": [
                {"id": 1, "name": "Tax Report 2024", "status": "Ready"},
                {"id": 2, "name": "Investment 3Q", "status": "Pending"}
            ]
        }
        return Response(data)
