#quizzes/serializers

from django.utils import timezone
from rest_framework import serializers
from .models import (
    Quiz, QuizCenter, QuizSettings, Question,
    Choice, QuizSubmission, Answer, StudentProfile
)
from accounts.serializers import GradeSerializer, CenterSerializer
from accounts.models import Grade, Center, StudentProfile
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.db import transaction
import re
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

class NullableImageField(serializers.ImageField):
    """
    A custom image field that allows an empty string "" as a valid value,
    which is then converted to None. This is used to signal image deletion.
    It also provides a clearer error message for nameless file uploads.
    """
    def to_internal_value(self, data):
        # Handle image deletion signal
        if data == '':
            return None
        
        # Check for nameless file uploads, which is a common client-side error.
        # A file object without a name will cause a cryptic FileExtensionValidator error.
        if hasattr(data, 'name') and not data.name:
            raise serializers.ValidationError(
                'The uploaded file has no name. Please ensure the client is sending a valid filename.'
            )
            
        return super().to_internal_value(data)
    
    def run_validators(self, value):
        """Skip validators when value is None (image deletion case)"""
        if value is None:
            return
        super().run_validators(value)

class ImageURLRepresentationMixin:
    def to_representation(self, instance):
        """Convert `image` to a full URL during serialization."""
        representation = super().to_representation(instance)
        request = self.context.get('request')
        # Check if the image field exists and has a value
        if 'image' in representation and representation['image']:
            if instance.image and hasattr(instance.image, 'url'):
                if request:
                    representation['image'] = request.build_absolute_uri(instance.image.url)
                else:
                    representation['image'] = instance.image.url
        return representation

class ChoiceSerializer(ImageURLRepresentationMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    image = NullableImageField(
        required=False, allow_null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )

    class Meta:
        model = Choice
        fields = ['id', 'text', 'image', 'is_correct']

class StudentChoiceSerializer(ImageURLRepresentationMixin, serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ['id', 'text', 'image']

class QuestionSerializer(ImageURLRepresentationMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    choices = ChoiceSerializer(many=True, required=True)
    image = NullableImageField(
        required=False, allow_null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )

    class Meta:
        model = Question
        fields = ['id', 'question_type', 'selection_type', 'text', 'points', 'image', 'choices', 'order']

    def validate(self, data):
        instance = self.instance
        
        # Determine the final state of the question's content for validation.
        final_text = data.get('text', getattr(instance, 'text', None))
        final_image = data.get('image', getattr(instance, 'image', None))
        
        # Handle explicit image deletion (when image is sent as "" or null).
        if 'image' in data and not data.get('image'):
            final_image = None

        if not final_text and not final_image:
            raise serializers.ValidationError("A question must have either text or an image.")

        choices_data = data.get('choices')
        selection_type = data.get('selection_type', getattr(instance, 'selection_type', None))

        if choices_data is not None:
            if not choices_data:
                raise serializers.ValidationError({"choices": "At least one choice is required."})

            existing_choices_map = {c.id: c for c in instance.choices.all()} if instance else {}
            choice_errors = []
            has_content_errors = False
            correct_choices_count = 0

            for choice_data in choices_data:
                # Manually validate each choice's content, as the nested serializer
                # does not receive the `instance` during parent validation.
                choice_id = choice_data.get('id')
                existing_choice = existing_choices_map.get(choice_id)

                final_text = choice_data.get('text') if 'text' in choice_data else getattr(existing_choice, 'text', None)
                final_image = choice_data.get('image') if 'image' in choice_data else getattr(existing_choice, 'image', None)

                if final_text == "":
                    final_text = None
                
                if 'image' in choice_data and not choice_data.get('image'):
                    final_image = None

                if not final_text and not final_image:
                    choice_errors.append({"non_field_errors": ["Each choice must have either text or an image."]})
                    has_content_errors = True
                else:
                    choice_errors.append({}) # Placeholder for correct error structure

                if choice_data.get('is_correct'):
                    correct_choices_count += 1

            if has_content_errors:
                raise serializers.ValidationError({"choices": choice_errors})

            if correct_choices_count == 0:
                raise serializers.ValidationError({"choices": "At least one choice must be marked as correct."})

            if selection_type == Question.SINGLE and correct_choices_count > 1:
                raise serializers.ValidationError({"choices": "Only one choice can be correct for a single-choice question."})

        return data

    def create(self, validated_data):
        choices_data = validated_data.pop('choices', [])
        question = Question.objects.create(**validated_data)
        # Use a loop to correctly save images, as bulk_create bypasses file saving.
        for choice_data in choices_data:
            Choice.objects.create(question=question, **choice_data)
        return question

    def update(self, instance, validated_data):
        choices_data = validated_data.pop('choices', None)

        # Update the Question instance's own fields using the parent's update method.
        # This correctly handles partial updates for the question's text, points, etc.
        instance = super().update(instance, validated_data)

        if choices_data is not None:
            existing_choices = {c.id: c for c in instance.choices.all()}
            incoming_choice_ids = {c.get('id') for c in choices_data if c.get('id')}

            # Delete choices that are in the DB but not in the incoming data.
            for choice_id in existing_choices:
                if choice_id not in incoming_choice_ids:
                    existing_choices[choice_id].delete()

            # Create or update choices
            for choice_data in choices_data:
                choice_id = choice_data.get('id')
                if choice_id:
                    # Update existing choice using the ChoiceSerializer for consistency.
                    choice_instance = existing_choices.get(choice_id)
                    if choice_instance:
                        choice_serializer = ChoiceSerializer(instance=choice_instance, data=choice_data, partial=True, context=self.context)
                        choice_serializer.is_valid(raise_exception=True)
                        choice_serializer.save()
                else:
                    # Create new choice using the ChoiceSerializer.
                    choice_serializer = ChoiceSerializer(data=choice_data, context=self.context)
                    choice_serializer.is_valid(raise_exception=True)
                    choice_serializer.save(question=instance)

        return instance

class StudentQuestionSerializer(QuestionSerializer):
    choices = StudentChoiceSerializer(many=True, read_only=True)

class QuestionInAnswerSerializer(ImageURLRepresentationMixin, serializers.ModelSerializer):
    """A lightweight serializer for displaying question details within an answer."""
    class Meta:
        model = Question
        fields = ['id', 'text', 'image']

class QuizCenterSerializer(serializers.ModelSerializer):
    center = CenterSerializer(read_only=True)
    center_id = serializers.PrimaryKeyRelatedField(
        queryset=Center.objects.all(),
        source='center',
        write_only=True
    )
    status = serializers.SerializerMethodField()

    class Meta:
        model = QuizCenter
        fields = ['center', 'center_id', 'open_date', 'close_date', 'status']

    def get_status(self, obj):
        now = timezone.now()
        if now < obj.open_date:
            return 'upcoming'
        if now > obj.close_date:
            return 'closed'
        return 'open'

    def validate(self, data):
        # For updates, if a date isn't provided, get it from the existing instance.
        # This ensures validation works correctly even on partial updates (PATCH).
        open_date = data.get('open_date', getattr(self.instance, 'open_date', None))
        close_date = data.get('close_date', getattr(self.instance, 'close_date', None))

        if open_date and close_date and close_date <= open_date:
            raise serializers.ValidationError({"close_date": "The close date must be after the open date."})
        return data

class QuizSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizSettings
        fields = ['timer_minutes', 'score_visibility', 'answers_visibility', 'question_order']

class QuizCreateSerializer(serializers.ModelSerializer):
    grade = GradeSerializer(read_only=True)
    grade_id = serializers.PrimaryKeyRelatedField(
        queryset=Grade.objects.all(),
        source='grade',
        write_only=True,
        required=True
    )
    centers = QuizCenterSerializer(
        many=True,
        source='quizcenter_set',
        required=True
    )
    settings = QuizSettingsSerializer(required=True)
    questions = QuestionSerializer(many=True, required=True)

    class Meta:
        model = Quiz
        fields = [
            'id', 'title', 'description', 'grade', 'grade_id', 'centers',
            'settings', 'questions'
        ]
        read_only_fields = ['id', 'teacher']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

    def create(self, validated_data):
        centers_data = validated_data.pop('quizcenter_set')
        settings_data = validated_data.pop('settings')
        questions_data = validated_data.pop('questions')
        teacher = self.context['request'].user.teacher_profile

        with transaction.atomic():
            quiz = Quiz.objects.create(teacher=teacher, **validated_data)
            QuizSettings.objects.create(quiz=quiz, **settings_data)

            # Create quiz centers
            QuizCenter.objects.bulk_create([
                QuizCenter(
                    quiz=quiz,
                    center=center_data['center'],
                    open_date=center_data['open_date'],
                    close_date=center_data['close_date']
                ) for center_data in centers_data
            ])

            # Create questions and choices
            for index, question_data in enumerate(questions_data):
                choices_data = question_data.pop('choices')
                question = Question.objects.create(quiz=quiz, order=index, **question_data)
                # Use a loop to correctly save images, as bulk_create bypasses file saving.
                for choice_data in choices_data:
                    Choice.objects.create(question=question, **choice_data)

        return quiz
    
    def update(self, instance, validated_data):
        # Pop nested data
        centers_data = validated_data.pop('quizcenter_set', None)
        settings_data = validated_data.pop('settings', None)
        questions_data = validated_data.pop('questions', None)

        with transaction.atomic():
            # Update Quiz instance's top-level fields by calling the parent's update method.
            # This is more robust and automatically handles any new fields added to the serializer.
            instance = super().update(instance, validated_data)

            # Update Settings
            if settings_data:
                QuizSettings.objects.update_or_create(quiz=instance, defaults=settings_data)

            # Update Centers
            if centers_data is not None:
                # Get IDs of incoming centers to determine which to delete
                current_center_ids = [c['center'].id for c in centers_data]
                instance.quizcenter_set.exclude(center_id__in=current_center_ids).delete()
                
                # Add or update the centers provided
                for center_data in centers_data:
                    QuizCenter.objects.update_or_create(
                        quiz=instance,
                        center=center_data['center'],
                        defaults={
                            'open_date': center_data['open_date'],
                            'close_date': center_data['close_date']
                        }
                    )

            # Update Questions - FIXED DELETION ORDER
            if questions_data is not None:
                existing_questions = {q.id: q for q in instance.questions.all()}
                updated_question_ids = []  # Track IDs of updated/created questions

                # Step 1: Update existing questions
                for index, q_data in enumerate(questions_data):
                    q_id = q_data.get('id')
                    q_data['order'] = index
                    
                    if q_id and q_id in existing_questions:
                        question_instance = existing_questions[q_id]
                        q_serializer = QuestionSerializer(
                            instance=question_instance, 
                            data=q_data, 
                            context=self.context, 
                            partial=True
                        )
                        q_serializer.is_valid(raise_exception=True)
                        updated_question = q_serializer.save()
                        updated_question_ids.append(updated_question.id)

                # Step 2: Create new questions
                for index, q_data in enumerate(questions_data):
                    q_id = q_data.get('id')
                    if not q_id:  # New question
                        q_serializer = QuestionSerializer(
                            data=q_data, 
                            context=self.context
                        )
                        q_serializer.is_valid(raise_exception=True)
                        new_question = q_serializer.save(quiz=instance)
                        updated_question_ids.append(new_question.id)

                # Step 3: Delete removed questions (after all updates)
                instance.questions.exclude(id__in=updated_question_ids).delete()
        
        return instance

class StudentSubmissionStatusSerializer(serializers.ModelSerializer):
    """
    Serializes a StudentProfile to mimic a QuizSubmission object for a
    teacher's progress view. It includes the submission status and handles
    cases where a submission does not yet exist.
    """
    # The top-level 'id' will be the submission's ID, which can be null.
    id = serializers.SerializerMethodField(method_name='get_submission_id')
    # 'student' will be the student's own profile ID.
    student = serializers.IntegerField(source='id', read_only=True)

    # New fields for student details
    student_name = serializers.CharField(source='full_name', read_only=True)
    phone_number = serializers.CharField(read_only=True) # Assumes 'phone_number' field on StudentProfile
    parent_phone_number = serializers.CharField(source='parent_number', read_only=True) # Source from StudentProfile.parent_number
    center = CenterSerializer(read_only=True)

    submission_status = serializers.SerializerMethodField()
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    is_submitted = serializers.SerializerMethodField()
    time_taken = serializers.SerializerMethodField()
    is_score_released = serializers.SerializerMethodField()
    are_answers_released = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            'id', 'student', 'student_name', 'phone_number', 'parent_phone_number',
            'center', 'start_time', 'end_time', 'score', 'is_submitted',
            'time_taken', 'is_score_released', 'are_answers_released', 'submission_status'
        ]
    
    def _is_quiz_closed(self, student_profile):
        """
        Helper to check if the quiz is closed for a specific student's center.
        Uses a pre-fetched map from the context for efficiency.
        """
        quiz_settings = self.context.get('quiz_settings')
        quiz_center_map = self.context.get('quiz_center_map', {})
        if not quiz_settings or not quiz_center_map:
            return False

        # Look up the specific QuizCenter for this student
        quiz_center = quiz_center_map.get(student_profile.center_id)
        if not quiz_center:
            return False # Student's center not assigned to this quiz

        # Calculate the effective release time
        effective_release_time = quiz_center.close_date
        if quiz_settings.timer_minutes > 0:
            try:
                effective_release_time += timedelta(minutes=quiz_settings.timer_minutes)
            except OverflowError:
                # If the timer value is huge, the release time is effectively infinite.
                # Therefore, the quiz is not yet closed.
                return False
        return timezone.now() > effective_release_time

    def _get_submission(self, obj):
        # Helper to avoid repeated lookups in the context map for the same student.
        return self.context.get('submission_map', {}).get(obj.id)

    def get_submission_id(self, obj):
        submission = self._get_submission(obj)
        return submission.id if submission else None

    def get_submission_status(self, obj):
        submission = self._get_submission(obj)
        if not submission:
            return "Not Started"
        if submission.is_submitted:
            return "Finished"
        # If not submitted, check if it has timed out.
        return "Finished" if submission.is_timed_out else "In Progress"

    def get_start_time(self, obj):
        submission = self._get_submission(obj)
        if submission and submission.start_time:
            return timezone.localtime(submission.start_time)
        return None

    def get_end_time(self, obj):
        submission = self._get_submission(obj)
        if not submission or not submission.start_time:
            return None

        # Priority 1: If an end_time is already saved in the database, use it.
        # This is the source of truth for both submitted and timed-out attempts.
        if submission.end_time:
            end_time_utc = submission.end_time
        # Priority 2: If no end_time is saved, but it's currently timed out (live check),
        # calculate a theoretical end time for display purposes.
        elif submission.is_timed_out:
            quiz_settings = self.context.get('quiz_settings')
            if quiz_settings and quiz_settings.timer_minutes > 0:
                try:
                    end_time_utc = submission.start_time + timedelta(minutes=quiz_settings.timer_minutes)
                except OverflowError:
                    end_time_utc = None
        else:
            end_time_utc = None

        if end_time_utc:
            return timezone.localtime(end_time_utc)
        return None

    def get_score(self, obj):
        submission = self._get_submission(obj)
        total_points = self.context.get('total_points', 0)

        if submission:
            # If submitted, show the actual score.
            if submission.is_submitted:
                return f"{submission.score:.1f} / {float(total_points):.1f}"
            # If timed out but not submitted, display the score as 0.
            if submission.is_timed_out:
                return f"0.0 / {float(total_points):.1f}"
        return None

    def get_is_submitted(self, obj):
        submission = self._get_submission(obj)
        # A submission is considered "submitted" in the response if it was
        # formally submitted or if it has timed out.
        return bool(submission and (submission.is_submitted or submission.is_timed_out))

    def get_time_taken(self, obj):
        submission = self._get_submission(obj)
        if not submission or not submission.start_time:
            return None
        if submission.is_submitted:
            return submission.time_taken()
        if submission.is_timed_out:
            return "Didn't submit"
        return "0 seconds"

    def get_is_score_released(self, obj):
        submission = self._get_submission(obj)
        quiz_settings = self.context.get('quiz_settings')
        if not quiz_settings:
            return False # Default safe

        is_closed = self._is_quiz_closed(obj)
        
        if quiz_settings.score_visibility == 'immediate':
            return True
        if quiz_settings.score_visibility == 'after_close':
            return is_closed
        if quiz_settings.score_visibility == 'manual':
            return submission.is_score_released if submission else False
        return False

    def get_are_answers_released(self, obj):
        submission = self._get_submission(obj)
        quiz_settings = self.context.get('quiz_settings')
        if not quiz_settings:
            return False # Default safe

        is_closed = self._is_quiz_closed(obj)

        if quiz_settings.answers_visibility == 'immediate':
            return True
        if quiz_settings.answers_visibility == 'after_close':
            return is_closed
        if quiz_settings.answers_visibility == 'manual':
            return submission.are_answers_released if submission else False
        return False

class QuizListSerializer(serializers.ModelSerializer):
    grade = GradeSerializer(read_only=True)
    center_times = serializers.SerializerMethodField()
    question_count = serializers.IntegerField(read_only=True)
    student_quiz_status = serializers.SerializerMethodField()
    submission_id = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = [
            'id', 'grade', 'title', 'description', 'center_times',
            'question_count', 'student_quiz_status', 'submission_id'
        ]

    def get_student_quiz_status(self, obj):
        request = self.context.get('request')
        if request and request.user.role == 'student':
            student_submission_list = getattr(obj, 'student_submission', [])
            if student_submission_list:
                submission = student_submission_list[0]
                # A quiz is considered 'submitted' if it's actually submitted OR if it has timed out.
                if submission.is_submitted or submission.is_timed_out:
                    return "submitted"
                return "in_progress"
            return "not_started"
        return None

    def get_submission_id(self, obj):
        request = self.context.get('request')
        if request and request.user.role == 'student':
            student_submission_list = getattr(obj, 'student_submission', [])
            if student_submission_list:
                submission = student_submission_list[0]
                # A quiz is considered 'submitted' if it's actually submitted OR if it has timed out.
                if submission.is_submitted or submission.is_timed_out:
                    return submission.id
        return None

    def to_representation(self, instance):
        """
        Customize the final output based on user role.
        """
        representation = super().to_representation(instance)
        request = self.context.get('request')

        if not (request and request.user.role == 'student'):
            representation.pop('student_quiz_status', None)
        
        if representation.get('student_quiz_status') != 'submitted':
            representation.pop('submission_id', None)

        return representation

    def get_center_times(self, obj):
        request = self.context.get('request')
        if not request:
            return QuizCenterSerializer(obj.quizcenter_set.all(), many=True).data

        if request.user.role == 'student':
            student_center = request.user.student_profile.center
            filtered_centers = obj.quizcenter_set.filter(center=student_center)
            return QuizCenterSerializer(filtered_centers, many=True).data

        if request.user.role in ['teacher', 'assistant']:
            teacher = request.user.teacher_profile if request.user.role == 'teacher' else request.user.assistant_profile.teacher
            teacher_centers = teacher.centers.all().order_by('name')
            assigned_centers_map = {qc.center_id: qc for qc in obj.quizcenter_set.all()}

            return [{
                "center": CenterSerializer(center).data,
                "open_date": assigned.open_date if (assigned := assigned_centers_map.get(center.id)) else None,
                "close_date": assigned.close_date if assigned else None,
                "status": "Not Assigned" if not assigned else self.get_status(assigned)
            } for center in teacher_centers]

        return QuizCenterSerializer(obj.quizcenter_set.all(), many=True).data

    def get_status(self, obj):
        now = timezone.now()
        if now < obj.open_date:
            return 'upcoming'
        if now > obj.close_date:
            return 'closed'
        return 'open'

class QuizDetailSerializer(serializers.ModelSerializer):
    grade = GradeSerializer()
    center_times = serializers.SerializerMethodField()
    settings = QuizSettingsSerializer()
    questions = serializers.SerializerMethodField()
    submission_status = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = [
            'id', 'title', 'description', 'grade', 'center_times', 'settings',
            'questions', 'submission_status'
        ]

    def get_center_times(self, obj):
        request = self.context.get('request')
        if request and request.user.role == 'student':
            student_center = request.user.student_profile.center
            queryset = obj.quizcenter_set.filter(center=student_center)
        else:
            queryset = obj.quizcenter_set.all()
        return QuizCenterSerializer(queryset, many=True).data

    def get_questions(self, obj):
        student_questions = self.context.get('student_questions')
        if student_questions is not None:
            return StudentQuestionSerializer(student_questions, many=True, context=self.context).data
        if self.context.get('request') and self.context['request'].user.role == 'student':
            return []
        return QuestionSerializer(obj.questions.all(), many=True, context=self.context).data

    def get_submission_status(self, obj):
        request = self.context.get('request')
        if request and request.user.role == 'student':
            try:
                submission = QuizSubmission.objects.get(
                    quiz=obj,
                    student=request.user.student_profile
                )
                # A quiz is considered 'submitted' if it's actually submitted OR if it has timed out.
                if submission.is_submitted or submission.is_timed_out:
                    return "submitted"
                return "in_progress"
            except QuizSubmission.DoesNotExist:
                return "not_started"
        return None

class AnswerCreateSerializer(serializers.ModelSerializer):
    question_id = serializers.PrimaryKeyRelatedField(
        queryset=Question.objects.all(),
        source='question',
        write_only=True
    )
    selected_choices = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Choice.objects.all(),
        required=True
    )

    class Meta:
        model = Answer
        fields = ['question_id', 'selected_choices']

    def validate(self, attrs):
        question = attrs['question']
        selected_choices = attrs.get('selected_choices', [])

        if question.selection_type == Question.SINGLE and len(selected_choices) > 1:
            raise serializers.ValidationError(
                "Only one choice can be selected for this question"
            )

        valid_choice_ids = set(question.choices.values_list('id', flat=True))
        selected_ids = {choice.id for choice in selected_choices}

        if not selected_ids.issubset(valid_choice_ids):
            raise serializers.ValidationError(
                "One or more selected choices do not belong to this question"
            )

        return attrs

class QuizSubmissionUpdateSerializer(serializers.Serializer):
    answers = AnswerCreateSerializer(many=True, required=True)

    def validate_answers(self, value):
        """
        Validates that the submitted answers correspond to the questions
        assigned to this submission.
        """
        submission = self.context['submission']  # Fixed typo in context key

        expected_question_ids = set(submission.answers.values_list('question_id', flat=True))  # Fixed variable name
        submitted_question_ids = {answer_data['question'].id for answer_data in value}

        # Allow partial submissions by checking if submitted questions are a valid
        # subset of the quiz's questions. This is crucial for timed-out quizzes
        # where a student may not have answered everything.
        if not submitted_question_ids.issubset(expected_question_ids):
            raise serializers.ValidationError(
                "One or more submitted answers do not belong to this quiz."
            )

        return value

    def update(self, instance, validated_data):
        """
        Updates the 'selected_choices' for the answers in the submission.
        `instance` is the QuizSubmission object.
        """
        answers_data = validated_data.get('answers')

        with transaction.atomic():
            # Efficiently clear all previous M2M relationships for this submission's answers
            Answer.selected_choices.through.objects.filter(answer__submission=instance).delete()

            # Map question_id to the existing answer_id for quick lookup
            answer_map = {ans.question_id: ans.id for ans in instance.answers.all()}

            # Prepare to bulk-create the new M2M relationships
            AnswerChoices = Answer.selected_choices.through
            through_instances = []
            for adata in answers_data:
                answer_id = answer_map[adata['question'].id]
                for choice in adata['selected_choices']:
                    through_instances.append(AnswerChoices(answer_id=answer_id, choice_id=choice.id))

            AnswerChoices.objects.bulk_create(through_instances)

        return instance

class QuizSubmissionConfirmationSerializer(serializers.ModelSerializer):
    submission_status = serializers.SerializerMethodField()

    class Meta:
        model = QuizSubmission
        fields = ['id', 'end_time', 'is_submitted', 'submission_status']

    def get_submission_status(self, obj):
        if not obj.start_time or not obj.end_time:
            return 'pending'

        timer_minutes = obj.quiz.settings.timer_minutes
        if timer_minutes == 0:
            return 'on_time'

        time_taken_seconds = (obj.end_time - obj.start_time).total_seconds()
        allowed_seconds = (timer_minutes * 60) + 60

        return 'late' if time_taken_seconds > allowed_seconds else 'on_time'

class SubmissionVisibilityMixin:
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = request.user if request else None

        # --- Dynamic Visibility Logic for ALL Roles ---
        settings = instance.quiz.settings
        
        # For a single submission, we can use its student's center for calculation.
        student_center = instance.student.center
        
        try:
            quiz_center = QuizCenter.objects.get(
                quiz=instance.quiz,
                center=student_center
            )
            effective_release_time = quiz_center.close_date
            if settings.timer_minutes > 0:
                try:
                    effective_release_time += timedelta(minutes=settings.timer_minutes)
                except OverflowError:
                    # If timer is too large, the release time is effectively infinite.
                    return False # Not closed yet

            is_quiz_closed = timezone.now() > effective_release_time

        except QuizCenter.DoesNotExist:
            is_quiz_closed = False

        # A submission is considered "finished" if it has been submitted or has timed out.
        submission_is_finished = instance.is_submitted or instance.is_timed_out

        # Determine dynamic release status
        score_is_visible = False
        if submission_is_finished: # A student can never see results before finishing
            if settings.score_visibility == 'immediate':
                score_is_visible = True
            elif settings.score_visibility == 'after_close':
                score_is_visible = is_quiz_closed
            elif settings.score_visibility == 'manual':
                score_is_visible = instance.is_score_released

        answers_are_visible = False
        if submission_is_finished: # A student can never see results before finishing
            if settings.answers_visibility == 'immediate':
                answers_are_visible = True
            elif settings.answers_visibility == 'after_close':
                answers_are_visible = is_quiz_closed
            elif settings.answers_visibility == 'manual':
                answers_are_visible = instance.are_answers_released

        # Update the response data with the effective status for all roles.
        data['is_score_released'] = score_is_visible
        data['are_answers_released'] = answers_are_visible

        # --- Role-Specific Data Hiding (for Students only) ---
        # Teachers/Assistants will always see the score and answers, but the flags above
        # will now correctly reflect the effective status.
        if user and user.role == 'student':
            if not score_is_visible:
                data.pop('score', None)
            
            if not answers_are_visible and 'answers' in data:
                del data['answers']

        return data

class QuizSubmissionSerializer(SubmissionVisibilityMixin, serializers.ModelSerializer):
    time_taken = serializers.SerializerMethodField()
    submission_status = serializers.SerializerMethodField()
    is_submitted = serializers.SerializerMethodField()
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()

    class Meta:
        model = QuizSubmission
        fields = [
            'id', 'student', 'start_time', 'end_time', 'score', 'is_submitted',
            'time_taken', 'is_score_released', 'are_answers_released', 'submission_status'
        ]

    def get_start_time(self, obj):
        if obj.start_time:
            return timezone.localtime(obj.start_time)
        return None

    def get_is_submitted(self, obj):
        return obj.is_submitted or obj.is_timed_out

    def get_end_time(self, obj):
        # Priority 1: If an end_time is already saved in the database, use it.
        if obj.end_time:
            end_time_utc = obj.end_time
        # Priority 2: If no end_time is saved, but it's currently timed out (live check),
        # calculate a theoretical end time for display purposes.
        elif obj.is_timed_out:
            if obj.quiz.settings.timer_minutes > 0 and obj.start_time:
                try:
                    end_time_utc = obj.start_time + timedelta(minutes=obj.quiz.settings.timer_minutes)
                except OverflowError:
                    end_time_utc = None
        else:
            end_time_utc = None
        if end_time_utc:
            return timezone.localtime(end_time_utc)
        return None

    def get_time_taken(self, obj):
        if obj.is_submitted:
            return obj.time_taken()
        if obj.is_timed_out:
            return "Didn't submit"
        return "0 seconds"

    def get_submission_status(self, obj):
        if obj.is_submitted or obj.is_timed_out:
            return "Finished"
        if obj.start_time:
            return "In Progress"
        return "Not Started"

class AnswerDetailSerializer(serializers.ModelSerializer):
    question = QuestionInAnswerSerializer(read_only=True)
    selected_choices = serializers.SerializerMethodField()
    choices = serializers.SerializerMethodField()
    selection_type = serializers.CharField(source='question.selection_type', read_only=True)

    class Meta:
        model = Answer
        fields = ['id', 'question', 'selection_type', 'choices', 'selected_choices', 'is_correct', 'points_earned']
        read_only_fields = ['id', 'is_correct', 'points_earned']

    def get_selected_choices(self, obj):
        return ChoiceSerializer(obj.selected_choices.all(), many=True, context=self.context).data

    def get_choices(self, obj):
        # Returns all choices for the question, marking correct ones.
        choices = obj.question.choices.all()
        return ChoiceSerializer(choices, many=True, context=self.context).data


class QuizSubmissionDetailSerializer(SubmissionVisibilityMixin, serializers.ModelSerializer):
    answers = AnswerDetailSerializer(many=True, read_only=True)
    time_taken = serializers.SerializerMethodField()
    submission_status = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    is_submitted = serializers.SerializerMethodField()
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()

    # Quiz Info
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    quiz_description = serializers.CharField(source='quiz.description', read_only=True)

    # Student Info
    student_id = serializers.CharField(source='student.student_id', read_only=True)
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    center = CenterSerializer(source='student.center', read_only=True)
    grade = GradeSerializer(source='student.grade', read_only=True)

    class Meta:
        model = QuizSubmission
        fields = [
            'id', 'quiz_title', 'quiz_description', 'student_id', 'student_name',
            'center', 'grade', 'start_time', 'end_time', 'score', 'is_submitted',
            'time_taken', 'answers', 'submission_status', 'is_score_released', 'are_answers_released'
        ]

    def get_start_time(self, obj):
        if obj.start_time:
            return timezone.localtime(obj.start_time)
        return None

    def get_is_submitted(self, obj):
        return obj.is_submitted or obj.is_timed_out

    def get_end_time(self, obj):
        # Priority 1: If an end_time is already saved in the database, use it.
        if obj.end_time:
            end_time_utc = obj.end_time
        # Priority 2: If no end_time is saved, but it's currently timed out (live check),
        # calculate a theoretical end time for display purposes.
        elif obj.is_timed_out:
            if obj.quiz.settings.timer_minutes > 0 and obj.start_time:
                try:
                    end_time_utc = obj.start_time + timedelta(minutes=obj.quiz.settings.timer_minutes)
                except OverflowError:
                    end_time_utc = None
        else:
            end_time_utc = None
        if end_time_utc:
            return timezone.localtime(end_time_utc)
        return None

    def get_score(self, obj):
        """Formats the score as 'X / Y' where Y is the total points for the quiz."""
        if obj.is_submitted or obj.is_timed_out:
            total_points = self.context.get('total_points', 0)
            score_to_display = obj.score if obj.is_submitted else 0.0
            # Format to one decimal place for consistency
            return f"{score_to_display:.1f} / {float(total_points):.1f}"
        return None

    def get_time_taken(self, obj):
        if obj.is_submitted:
            return obj.time_taken()
        if obj.is_timed_out:
            return "Didn't submit"
        return "0 seconds"

    def get_submission_status(self, obj):
        if obj.is_timed_out:
            return 'late'

        if not obj.is_submitted:
            return 'in_progress'

        if not obj.start_time or not obj.end_time:
            return 'pending' # Should be rare

        timer_minutes = obj.quiz.settings.timer_minutes
        if timer_minutes == 0:
            return 'on_time'

        time_taken_seconds = (obj.end_time - obj.start_time).total_seconds()
        allowed_seconds = (timer_minutes * 60) + 60

        return 'late' if time_taken_seconds > allowed_seconds else 'on_time'