from rest_framework import serializers
from .models import UploadedFile, ReconciliationJob

class UploadedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = '__all__'

class ReconciliationJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationJob
        fields = '__all__'
