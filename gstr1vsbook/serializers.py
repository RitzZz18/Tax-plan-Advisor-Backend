from rest_framework import serializers


class GSTR1ReconciliationRequestSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="Excel file with Books data")
    session_id = serializers.CharField(help_text="Session ID from OTP verification")
    reco_type = serializers.ChoiceField(
        choices=["MONTHLY", "QUARTERLY", "FY"],
        help_text="Reconciliation type"
    )
    year = serializers.IntegerField(help_text="FY start year (e.g., 2025)")
    month = serializers.IntegerField(
        required=False, 
        allow_null=True,
        min_value=1, 
        max_value=12,
        help_text="Month (1-12), required for MONTHLY"
    )
    quarter = serializers.ChoiceField(
        choices=["Q1", "Q2", "Q3", "Q4"],
        required=False,
        allow_null=True,
        help_text="Quarter, required for QUARTERLY"
    )
    
    def validate(self, data):
        reco_type = data.get("reco_type")
        
        if reco_type == "MONTHLY" and not data.get("month"):
            raise serializers.ValidationError({"month": "Month is required for MONTHLY reco type"})
        
        if reco_type == "QUARTERLY" and not data.get("quarter"):
            raise serializers.ValidationError({"quarter": "Quarter is required for QUARTERLY reco type"})
        
        return data