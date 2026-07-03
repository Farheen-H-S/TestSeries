from rest_framework import serializers
from .models import Subject, Chapter

class SubjectSerializer(serializers.ModelSerializer):
    """
    Serializer for the Subject model.
    """
    class Meta:
        model = Subject
        fields = ['subject_id', 'name', 'exam_level']


class ChapterSerializer(serializers.ModelSerializer):
    """
    Serializer for the Chapter model.
    """
    class Meta:
        model = Chapter
        fields = ['chapter_id', 'chapter_name', 'chapter_order']
