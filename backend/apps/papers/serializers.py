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
        # 1. Normalize whitespace from text fields if they are supplied
        if 'question_number' in attrs and attrs['question_number'] is not None:
            attrs['question_number'] = " ".join(attrs['question_number'].strip().split())

        for field in ['question_text', 'answer_text']:
            if field in attrs and attrs[field] is not None:
                attrs[field] = attrs[field].strip()

        # If it's an update request (we have an instance), validate required fields
        if self.instance:
            question_number = attrs.get('question_number', self.instance.question_number)
            question_text = attrs.get('question_text', self.instance.question_text)
            answer_text = attrs.get('answer_text', self.instance.answer_text)
            chapter = attrs.get('chapter', self.instance.chapter)

            if not question_number or question_number.strip() == "":
                raise serializers.ValidationError({"question_number": "Question number is required."})
            if not question_text or question_text.strip() == "":
                raise serializers.ValidationError({"question_text": "Question text is required."})
            if not answer_text or answer_text.strip() == "":
                raise serializers.ValidationError({"answer_text": "Answer text is required."})
            if chapter is None:
                raise serializers.ValidationError({"chapter": "Chapter is required."})

            # Check that the chapter belongs to the subject associated with the question's document
            document = attrs.get('document', self.instance.document)
            if chapter and document and chapter.subject_id != document.subject_id:
                raise serializers.ValidationError({
                    "chapter": f"Chapter '{chapter.chapter_name}' does not belong to the subject '{document.subject.name}'."
                })

        # 2. Synchronize content HTML only when text updates are supplied
        if 'question_text' in attrs:
            from apps.extraction.services.html_formatter import text_to_html
            attrs['question_content'] = text_to_html(attrs['question_text'])
            
        if 'answer_text' in attrs:
            from apps.extraction.services.html_formatter import text_to_html
            attrs['answer_content'] = text_to_html(attrs['answer_text'])

        return attrs

class GeneratedPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPaper
        fields = '__all__'

class GeneratedPaperQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedPaperQuestion
        fields = '__all__'
