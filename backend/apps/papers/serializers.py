from rest_framework import serializers
from .models import Question, GeneratedPaper, GeneratedPaperQuestion
from apps.extraction.services.html_formatter import text_to_html

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
            'hierarchy_key',
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

    def validate(self, attrs):
        # 1. Structural checks on update inputs (only if supplied in attrs)
        if 'question_number' in attrs:
            val = attrs['question_number']
            if val is None or str(val).strip() == "":
                raise serializers.ValidationError({"question_number": "Question number cannot be blank."})

        if 'question_text' in attrs:
            val = attrs['question_text']
            if val is None or str(val).strip() == "":
                raise serializers.ValidationError({"question_text": "Question text cannot be blank."})

        if 'answer_text' in attrs:
            val = attrs['answer_text']
            if val is None or str(val).strip() == "":
                raise serializers.ValidationError({"answer_text": "Answer text cannot be blank."})

        if 'chapter' in attrs:
            chapter = attrs['chapter']
            if chapter is None:
                raise serializers.ValidationError({"chapter": "Chapter is required."})

            # Check that the chapter belongs to the subject associated with the question's document
            if self.instance:
                document = attrs.get('document', self.instance.document)
                if document and chapter.subject_id != document.subject_id:
                    raise serializers.ValidationError({
                        "chapter": f"Chapter '{chapter.chapter_name}' does not belong to the subject '{document.subject.name}'."
                    })
        return attrs

    def update(self, instance, validated_data):
        # 2. Perform whitespace trimming / normalization mutations inside update()
        if 'question_number' in validated_data and validated_data['question_number'] is not None:
            validated_data['question_number'] = validated_data['question_number'].strip()

        if 'question_text' in validated_data and validated_data['question_text'] is not None:
            validated_data['question_text'] = validated_data['question_text'].strip()
            validated_data['question_content'] = text_to_html(validated_data['question_text'])

        if 'answer_text' in validated_data and validated_data['answer_text'] is not None:
            validated_data['answer_text'] = validated_data['answer_text'].strip()
            validated_data['answer_content'] = text_to_html(validated_data['answer_text'])

        return super().update(instance, validated_data)

class GeneratedPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPaper
        fields = '__all__'

class GeneratedPaperQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPaperQuestion
        fields = '__all__'
