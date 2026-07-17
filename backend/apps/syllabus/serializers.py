from rest_framework import serializers
from .models import Subject, Chapter

def normalize_whitespace(value):
    if value is None:
        return None
    return " ".join(value.strip().split())


class SubjectSerializer(serializers.ModelSerializer):
    chapters_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Subject
        fields = ['subject_id', 'name', 'exam_level', 'chapters_count', 'created_at', 'updated_at']
        read_only_fields = ['chapters_count', 'created_at', 'updated_at']

    def validate(self, attrs):
        name = attrs.get('name')
        exam_level = attrs.get('exam_level')

        if name is not None:
            name = normalize_whitespace(name)
            attrs['name'] = name

            if not name:
                raise serializers.ValidationError({"name": "Subject name cannot be blank."})

        # Fetch values on update if not provided in request
        if self.instance:
            name = name if name is not None else self.instance.name
            exam_level = exam_level if exam_level is not None else self.instance.exam_level

        # Case-insensitive duplicate check within the same exam_level (checking all records to prevent DB unique constraint violation)
        if name and exam_level:
            qs = Subject.objects.filter(name__iexact=name, exam_level=exam_level)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "name": f"A subject with the name '{name}' already exists for the '{exam_level}' exam level."
                })

        return attrs


class ChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapter
        fields = ['chapter_id', 'chapter_name', 'chapter_order']
        read_only_fields = ['chapter_order']

    def validate(self, attrs):
        chapter_name = attrs.get('chapter_name')

        if chapter_name is not None:
            chapter_name = normalize_whitespace(chapter_name)
            attrs['chapter_name'] = chapter_name

            if not chapter_name:
                raise serializers.ValidationError({"chapter_name": "Chapter name cannot be blank."})

        # Context-dependent check
        view = self.context.get('view')
        subject = None
        if view and hasattr(view, 'kwargs'):
            subject_id = view.kwargs.get('subject_id')
            if subject_id:
                try:
                    subject = Subject.objects.get(pk=subject_id, is_active=True)
                except Subject.DoesNotExist:
                    raise serializers.ValidationError({"chapter_name": "Invalid subject."})

        if self.instance:
            subject = self.instance.subject
            chapter_name = chapter_name if chapter_name is not None else self.instance.chapter_name

        if subject and chapter_name:
            qs = Chapter.objects.filter(subject=subject, chapter_name__iexact=chapter_name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "chapter_name": f"A chapter with the name '{chapter_name}' already exists in this subject."
                })

        return attrs
