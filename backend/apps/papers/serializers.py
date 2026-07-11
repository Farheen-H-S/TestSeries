from rest_framework import serializers
from .models import Question, GeneratedPaper, GeneratedPaperQuestion

class QuestionSerializer(serializers.ModelSerializer):
    chapter_name = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'question_id',
            'parent_question',
            'document',
            'chapter',
            'chapter_name',
            'question_number',
            'sub_question_label',
            'question_content',
            'question_text',
            'answer_content',
            'answer_text',
            'question_type',
            'instruction_type',
            'marks',
            'source_page',
            'created_at',
        ]

    def get_chapter_name(self, obj):
        chapter = getattr(obj, "chapter", None)
        return getattr(chapter, "chapter_name", None)

class GeneratedPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPaper
        fields = '__all__'

class GeneratedPaperQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPaperQuestion
        fields = '__all__'
