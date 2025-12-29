from rest_framework import serializers

class GSTR1DownloadSerializer(serializers.Serializer):
    gstin = serializers.CharField(max_length=15, required=True)
    api_key = serializers.CharField(required=True)
    access_token = serializers.CharField(required=True)
    download_type = serializers.ChoiceField(choices=['fy', 'quarterly', 'monthly'], required=True)
    fy = serializers.CharField(max_length=7, required=False, allow_blank=True)
    quarter = serializers.CharField(max_length=1, required=False, allow_blank=True)
    year = serializers.CharField(max_length=4, required=False, allow_blank=True)
    month = serializers.CharField(max_length=2, required=False, allow_blank=True)
    
    def validate(self, data):
        if data['download_type'] == 'fy' and not data.get('fy'):
            raise serializers.ValidationError("FY is required for FY download")
        if data['download_type'] == 'quarterly' and (not data.get('fy') or not data.get('quarter')):
            raise serializers.ValidationError("FY and quarter are required for quarterly download")
        if data['download_type'] == 'monthly' and (not data.get('year') or not data.get('month')):
            raise serializers.ValidationError("Year and month are required for monthly download")
        return data
