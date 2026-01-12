from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, ConsultantClientLink
from django.contrib.auth import authenticate

# --- Role Enum for Frontend ---
# Make sure frontend knows: Consultant vs Client

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['user', 'role', 'phone_number', 'company_name']

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        user = authenticate(**data)
        if user and user.is_active:
            return user
        raise serializers.ValidationError("Invalid Credentials")

class ConsultantSignupSerializer(serializers.ModelSerializer):
    """
    For registering a new Consultant.
    """
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['username', 'password', 'email', 'first_name', 'last_name']
        
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        # Ensure profile is Consultant
        # (Signal creates generic profile, we update it)
        user.profile.role = UserProfile.Role.CONSULTANT
        user.profile.save()
        return user

class CreateClientSerializer(serializers.ModelSerializer):
    """
    Used by Consultant to create a Client.
    """
    phone_number = serializers.CharField(required=False)
    company_name = serializers.CharField(required=False)
    
    class Meta:
        model = User
        fields = ['username', 'password', 'email', 'first_name', 'last_name', 'phone_number', 'company_name']
        extra_kwargs = {'password': {'write_only': True}}
        
    def create(self, validated_data):
        phone = validated_data.pop('phone_number', '')
        company = validated_data.pop('company_name', '')
        
        user = User.objects.create_user(**validated_data)
        
        user.profile.role = UserProfile.Role.CLIENT
        user.profile.phone_number = phone
        user.profile.company_name = company
        user.profile.save()
        
        return user

class ClientDashboardSerializer(serializers.ModelSerializer):
    """
    Minimal data for the client list in Consultant Dashboard.
    """
    username = serializers.CharField(source='user.username')
    email = serializers.CharField(source='user.email')
    
    class Meta:
        model = UserProfile
        fields = ['id', 'username', 'email', 'company_name', 'phone_number']
