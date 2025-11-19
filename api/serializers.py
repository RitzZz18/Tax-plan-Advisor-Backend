from rest_framework import serializers

class IncomeSerializer(serializers.Serializer):
    type = serializers.CharField()
    customType = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.FloatField()

class InvestmentRequestSerializer(serializers.Serializer):
    incomes = IncomeSerializer(many=True)
    expectedReturn = serializers.ChoiceField(choices=['low', 'medium', 'high'])
    riskAppetite = serializers.ChoiceField(choices=['low', 'medium', 'high'])
    investmentMode = serializers.ChoiceField(choices=['percent', 'amount'])
    investmentValue = serializers.FloatField()
