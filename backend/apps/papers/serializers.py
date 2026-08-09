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


# ---------------------------------------------------------------------------
# Generation serializers
# ---------------------------------------------------------------------------

import re
from apps.documents.models import Document

_VALID_QUESTION_TYPES = {'THEORY', 'PRACTICAL', 'CASE_STUDY', 'MCQ', 'MIXED'}
_VALID_MODULES = {'RTP', 'PYQ', 'MOCK'}
_VALID_EXAM_MONTHS = {m.value for m in Document.ExamMonth}


def _validate_paper_title(value: str) -> str:
    """Strip, truncate, and fallback to 'Practice Paper' if empty or short."""
    value = (value or '').strip()
    if not value or len(value) < 1:
        return 'Practice Paper'
    if len(value) > 100:
        return value[:100]
    return value


class GenerationFilterSerializer(serializers.Serializer):
    """
    Validates the filter payload sent to the preview endpoint.
    Enforces module-dependent field requirements and cross-field rules with smart defaults.
    """
    paper_title = serializers.CharField(required=False, default='Practice Paper', allow_blank=True)
    subject_id = serializers.IntegerField(required=True)
    module = serializers.CharField(required=True)

    # Module-dependent constraints — default defaults applied if missing
    total_marks = serializers.IntegerField(required=False, allow_null=True, default=None)
    question_count = serializers.IntegerField(required=False, allow_null=True, default=None)

    # Optional filters
    chapter_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    question_type = serializers.CharField(required=False, allow_null=True, default=None)
    year_from = serializers.IntegerField(required=False, allow_null=True, default=None)
    year_to = serializers.IntegerField(required=False, allow_null=True, default=None)
    exam_month = serializers.CharField(required=False, allow_null=True, default=None)

    def validate_paper_title(self, value):
        return _validate_paper_title(value)

    def validate_module(self, value):
        if value not in _VALID_MODULES:
            raise serializers.ValidationError(
                f"Module must be one of: {', '.join(sorted(_VALID_MODULES))}."
            )
        return value

    def validate_question_type(self, value):
        if value is not None and value not in _VALID_QUESTION_TYPES:
            raise serializers.ValidationError(
                f"Question type must be one of: {', '.join(sorted(_VALID_QUESTION_TYPES))}."
            )
        return value

    def validate_exam_month(self, value):
        if value is not None and value not in _VALID_EXAM_MONTHS:
            raise serializers.ValidationError(
                f"Invalid exam month: '{value}'."
            )
        return value

    def validate(self, attrs):
        module = attrs.get('module')
        total_marks = attrs.get('total_marks')
        question_count = attrs.get('question_count')
        chapter_ids = attrs.get('chapter_ids', [])
        year_from = attrs.get('year_from')
        year_to = attrs.get('year_to')

        # Auto-fallback to default paper_title if empty or invalid
        if not attrs.get('paper_title'):
            attrs['paper_title'] = 'Practice Paper'

        # chapter_ids only allowed for RTP
        if chapter_ids and module != 'RTP':
            attrs['chapter_ids'] = []

        # Marks-constrained modules default to 50 marks if unspecified
        if module in ('PYQ', 'MOCK'):
            if not total_marks or total_marks <= 0:
                attrs['total_marks'] = 50
            attrs['question_count'] = None

        # Count-constrained module defaults to 5 questions if unspecified
        if module == 'RTP':
            if not question_count or question_count <= 0:
                attrs['question_count'] = 5
            attrs['total_marks'] = None

        # Year range validation
        if year_from is not None and year_to is not None:
            if year_from > year_to:
                raise serializers.ValidationError({
                    'year_from': "year_from must be less than or equal to year_to."
                })

        return attrs


class PDFGenerationSerializer(serializers.Serializer):
    """
    Validates the payload sent to the question-paper and answer-sheet endpoints.
    subject_id and module are NOT included — they are derived from the loaded groups.
    """
    paper_title = serializers.CharField(required=True)
    root_question_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        allow_empty=False,
    )
    show_source = serializers.BooleanField(required=False, default=False)

    def validate_paper_title(self, value):
        return _validate_paper_title(value)

    def validate_root_question_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate IDs in root_question_ids.")
        return value
