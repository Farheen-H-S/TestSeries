from rest_framework import serializers
from .models import Question, GeneratedPaper, GeneratedPaperQuestion

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = '__all__'

class GeneratedPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPaper
        fields = '__all__'

class GeneratedPaperQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPaperQuestion
        fields = '__all__'
