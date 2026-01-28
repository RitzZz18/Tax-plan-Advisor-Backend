from rest_framework import serializers
from datetime import datetime


class TransactionSerializer(serializers.Serializer):
    """Serializer for a single transaction"""
    # Deductee details
    deductee_name = serializers.CharField(max_length=200)
    deductee_pan = serializers.CharField(max_length=10, required=False, allow_blank=True, allow_null=True)
    no_pan_available = serializers.BooleanField(required=False, default=False)
    
    # Transaction details
    section_code = serializers.CharField(max_length=20)
    amount = serializers.FloatField(min_value=0)
    category = serializers.ChoiceField(choices=[
        ("Company / Firm / Co-operative Society / Local Authority", "Company / Firm / Co-operative Society / Local Authority"),
        ("Individual / HUF", "Individual / HUF")
    ])
    pan_available = serializers.BooleanField()
    deduction_date = serializers.DateField()
    payment_date = serializers.DateField()
    threshold_type = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    annual_threshold_exceeded = serializers.BooleanField(required=False, default=False)
    selected_slab = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    selected_condition = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    threshold_exceeded_before = serializers.BooleanField(required=False, default=False)


class DeductorSerializer(serializers.Serializer):
    """Serializer for deductor details"""
    deductor_name = serializers.CharField(max_length=200)
    tan_number = serializers.CharField(max_length=10)
    entity_name = serializers.CharField(max_length=200)
    
    def validate_tan_number(self, value):
        """
        Validate TAN format:
        - First 3 characters (A-Z): Jurisdiction code
        - 4th character (A-Z): Initial of the deductor
        - Next 5 characters (0-9): Numeric
        - Last character (A-Z): Alphabet
        """
        import re
        value = value.upper()
        if not re.match(r'^[A-Z]{3}[A-Z][0-9]{5}[A-Z]$', value):
            raise serializers.ValidationError(
                "Invalid TAN format. Expected: ABCD12345E (3 letters + 1 letter + 5 digits + 1 letter)"
            )
        return value


class CalculateRequestSerializer(serializers.Serializer):
    """Serializer for TDS calculation request"""
    deductor = DeductorSerializer()
    transactions = TransactionSerializer(many=True)
    
    def validate_transactions(self, value):
        if not value:
            raise serializers.ValidationError("At least one transaction is required")
        return value


class ExcelRequestSerializer(serializers.Serializer):
    """Serializer for Excel generation request"""
    deductor = DeductorSerializer()
    results = serializers.ListField(child=serializers.DictField())
