# quizzes/views.py

from django.db.models import Prefetch, Count, F, Subquery, OuterRef, Sum
from .models import Quiz, Question, QuizSubmission, Answer, Choice, QuizSettings, QuizCenter
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from accounts.permissions import IsTeacher, IsAssistant, IsStudent
from .serializers import QuizCreateSerializer, QuizListSerializer, QuizDetailSerializer, QuestionSerializer, StudentQuestionSerializer, QuizSubmissionUpdateSerializer, QuizSubmissionSerializer, QuizSubmissionDetailSerializer, QuizSubmissionConfirmationSerializer, StudentSubmissionStatusSerializer , QuizSettingsSerializer
from .permissions import IsQuizOwnerOrAssistant, CanTakeQuiz
from accounts.models import StudentProfile, Grade, Center
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from collections import defaultdict
from datetime import timedelta
import json
import random
import re

class NestedMultipartParser:
    """
    Parses flat multipart/form-data with bracket notation (e.g., questions[0][text])
    into a nested dictionary structure that DRF serializers can understand.
    
    This is necessary because HTML forms submit nested data as flat key-value pairs.
    For example, a structure like:
    { "questions": [ { "text": "What is 2+2?", "image": <File> } ] }
    is sent as:
    - questions[0][text]: "What is 2+2?"
    - questions[0][image]: <File object>
    
    This parser reconstructs the original nested dictionary.
    """

    def __init__(self, data, files):
        self.data = {**data.dict(), **files.dict()}

    def _parse_key(self, key, value):
        """Improved to handle files explicitly."""
        """
        Parses 'questions[0][choices][1][text]' into ('questions', ['0', 'choices', '1', 'text']).
        """
        match = re.match(r'^([^\[]+)((?:\[[^\]]*\])*)$', key)
        if not match: return key, []
        root, nested_part = match.groups()
        return root, re.findall(r'\[([^\]]*)\]', nested_part)
        


    
    def _reconstruct(self, data):
        """
        Recursively reconstructs dictionaries that should be lists.
        Handles both lists (numeric keys) and nested dictionaries.
        """
        if not isinstance(data, dict):
            return data
        
        # If it's an empty dictionary, it can't be a list, so return it as is.
        if not data:
            return {}

        if all(k.isdigit() for k in data.keys()):  # List detection
            # This block is now only entered if there are numeric keys.
            max_index = max(int(k) for k in data.keys())
            result_list = [None] * (max_index + 1)
            for key, value in data.items():
                result_list[int(key)] = self._reconstruct(value)
            return result_list
        
        return {key: self._reconstruct(value) for key, value in data.items()}

    def parse(self):
        """
        Parses the flat multipart data into a nested dictionary.
        """
        nested_data = defaultdict(dict)
        flat_data = {}

    
        for key, value in self.data.items():  # Process all items including files
            root, nested_keys = self._parse_key(key, value)  # Pass the value to _parse_key
            if nested_keys:  # Still nested?
                 self._set_nested_value(nested_data, root, nested_keys, value)
            else:   # Simple case
                 flat_data[key] = value

        reconstructed_data = self._reconstruct(nested_data) # Nested parts
        return {**flat_data, **reconstructed_data}  # Combine nested with simple


    def _set_nested_value(self, data, root, keys, value):
        """
        Sets the value in the nested structure using the list of keys.
        """
        current = data.setdefault(root, {})  # Initialize root if needed
        for i, key in enumerate(keys):
             if i == len(keys) - 1:  # Last level, set the value
                  current[key] = value
             else:   # Not at the last level yet, ensure the next level exists (dict)
                  next_level = current.get(key)
                  if next_level is None:
                       current[key] = {}
                       current = current[key]
                  elif isinstance(next_level, dict):
                       current = next_level  # Move down the structure
                  else:  # Handle Error: existing value should be a dict
                       raise ValueError(f"Conflicting data structure at key path: {root}[{']['.join(keys[:i+1])}]")

# Quiz Views
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsTeacher | IsAssistant])
def create_quiz(request):
    """Create a new quiz with settings, questions, and center times."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Use startswith to handle the boundary in the Content-Type header
        if request.content_type.startswith('multipart/form-data'):
            # Reconstruct nested data from flat multipart structure
            parser = NestedMultipartParser(request.data, request.FILES)
            data = parser.parse()
        else:
            # Handle raw JSON for testing or non-file uploads
            data = request.data

        serializer = QuizCreateSerializer(data=data, context={'request': request})
        
        if not serializer.is_valid():
            logger.error(f"Serializer validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            quiz = serializer.save()
            # Re-fetch the quiz with related objects
            quiz_for_response = Quiz.objects.prefetch_related(
                Prefetch('quizcenter_set', queryset=QuizCenter.objects.select_related('center'))
            ).select_related('grade', 'settings').annotate(
                question_count=Count('questions', distinct=True)
            ).get(pk=quiz.pk)
            
            return Response(
                QuizListSerializer(quiz_for_response, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
            
    except ValidationError as e:
        logger.exception("Quiz creation validation error")
        return Response({'detail': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Quiz creation failed")
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_quizzes(request):
    """List quizzes based on user role"""
    user = request.user
    # Optimize query to prefetch related data needed by the serializer
    queryset = Quiz.objects.prefetch_related(
        Prefetch('quizcenter_set', queryset=QuizCenter.objects.select_related('center'))
    ).select_related('grade', 'teacher').annotate(
        question_count=Count('questions', distinct=True)
    )

    if user.role == 'teacher':
        quizzes = queryset.filter(teacher=user.teacher_profile)
    elif user.role == 'assistant':
        teacher = user.assistant_profile.teacher
        quizzes = queryset.filter(teacher=teacher)
    elif user.role == 'student':
        student = user.student_profile
        quizzes = queryset.filter(
            grade=student.grade,
            quizcenter__center=student.center
        ).prefetch_related(
            # Prefetch submission status for the current student to avoid N+1 queries in serializer
            Prefetch('submissions', 
                    queryset=QuizSubmission.objects.filter(student=student),
                    to_attr='student_submission'
            )
        ).distinct()
    else:
        quizzes = Quiz.objects.none()
    
    serializer = QuizListSerializer(quizzes, many=True, context={'request': request})
    
    # Custom sorting logic for teachers and assistants
    if user.role in ['teacher', 'assistant']:
        serialized_data = serializer.data

        # Determine if any quizzes are currently open or upcoming
        has_active_or_upcoming = any(
            any(ct['status'] in ['open', 'upcoming'] for ct in quiz['center_times'])
            for quiz in serialized_data
        )
        
        # If no quizzes are open or upcoming, sort the entire list alphabetically by title
        if not has_active_or_upcoming and serialized_data:
            sorted_data = sorted(serialized_data, key=lambda q: q['title'])
            return Response(sorted_data)

        # Otherwise, apply the multi-level sorting logic
        def get_sort_key(quiz):
            """Generates a tuple for sorting quizzes based on their primary status."""
            statuses = [ct['status'] for ct in quiz['center_times']]
            
            # 1. Determine primary status
            if 'open' in statuses:
                primary_status = 'open'
            elif 'upcoming' in statuses:
                primary_status = 'upcoming'
            elif 'closed' in statuses:
                primary_status = 'closed'
            else: # Should only be 'not_assigned'
                primary_status = 'Not Assigned'
            
            # 2. Define sort priority based on status
            priority_map = {'open': 1, 'upcoming': 2, 'closed': 3, 'not_assigned': 4}
            priority = priority_map.get(primary_status, 99)
            
            # 3. Define secondary sort value
            if primary_status == 'upcoming':
                # Get all valid open dates for upcoming centers
                upcoming_dates = [
                    ct['open_date'] for ct in quiz['center_times'] 
                    if ct['status'] == 'upcoming' and ct['open_date']
                ]
                
                # Only calculate min if we have dates
                if upcoming_dates:
                    min_open_date = min(upcoming_dates)
                    return (priority, min_open_date, quiz['title'])
                
            return (priority, quiz['title'])

        sorted_data = sorted(serialized_data, key=get_sort_key)
        return Response(sorted_data)

    return Response(serializer.data)

# quizzes/views.py

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def quiz_detail_or_update(request, quiz_id):
    """
    Handles retrieving (GET) a quiz for authorized users and updating (PUT) for teachers/assistants.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Fetch the quiz once for both methods.
    queryset = Quiz.objects.select_related('grade', 'settings', 'teacher').prefetch_related(
        Prefetch('quizcenter_set', queryset=QuizCenter.objects.select_related('center')),
        Prefetch('questions', queryset=Question.objects.prefetch_related('choices'))
    )
    quiz = get_object_or_404(queryset, id=quiz_id)

    if request.method == 'GET':
        # Handle permissions for GET request based on user role
        user = request.user
        
        if user.role == 'student':
            student = user.student_profile
            
            # Find the student's submission for this quiz.
            try:
                submission = QuizSubmission.objects.get(
                    quiz=quiz,
                    student=student
                )
            except QuizSubmission.DoesNotExist:
                # If no submission exists at all, they haven't even started.
                return Response(
                    {'detail': 'You have not started this quiz.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Check if the quiz has been started.
            if not submission.start_time:
                return Response(
                    {'detail': 'You must start the quiz before you can view its details.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # A student cannot view details after submitting or timing out.
            if submission.is_submitted or submission.is_timed_out:
                return Response({'detail': 'You cannot view quiz details after submission.'}, status=status.HTTP_403_FORBIDDEN)
            
            # Fetch the questions in the order they were presented to the student
            answers = Answer.objects.filter(submission=submission).select_related('question').order_by('order')
            student_questions = [answer.question for answer in answers]
            
            # Pass the ordered questions to the serializer via context
            serializer_context = {'request': request, 'student_questions': student_questions}
            serializer = QuizDetailSerializer(quiz, context=serializer_context)
            return Response(serializer.data)

        elif user.role in ['teacher', 'assistant']:
            # A teacher/assistant can view details if they own the quiz.
            if not IsQuizOwnerOrAssistant().has_object_permission(request, None, quiz):
                return Response({'detail': 'You do not have permission for this quiz.'}, status=status.HTTP_403_FORBIDDEN)
            
            serializer = QuizDetailSerializer(quiz, context={'request': request})
            return Response(serializer.data)
        
        # Deny other roles by default for GET
        return Response({'detail': 'Permission denied for your role.'}, status=status.HTTP_403_FORBIDDEN)

    elif request.method == 'PUT':
        # PUT is only for Teacher/Assistant who own the quiz
        if not (request.user.role in ['teacher', 'assistant']):
             return Response({'detail': 'You do not have permission to perform this action.'}, status=status.HTTP_403_FORBIDDEN)

        if not IsQuizOwnerOrAssistant().has_object_permission(request, None, quiz):
            return Response({'detail': 'You do not have permission for this quiz'}, status=status.HTTP_403_FORBIDDEN)

        try:
            if request.content_type.startswith('multipart/form-data'):
                parser = NestedMultipartParser(request.data, request.FILES)
                data = parser.parse()
            else:
                data = request.data

            serializer = QuizCreateSerializer(instance=quiz, data=data, context={'request': request})
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                updated_quiz = serializer.save()

                # Recalculate scores for any existing submissions
                submissions_to_update = []
                submitted_attempts = QuizSubmission.objects.filter(quiz=updated_quiz, is_submitted=True)
                for submission in submitted_attempts:
                    submission.score = submission.calculate_score()
                    submissions_to_update.append(submission)

                if submissions_to_update:
                    QuizSubmission.objects.bulk_update(submissions_to_update, ['score'])

                # Use the detail serializer for the response
                return Response(QuizDetailSerializer(updated_quiz, context={'request': request}).data)

        except Exception as e:
            logger.exception("Quiz update failed")
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsTeacher | IsAssistant])
def delete_quiz(request, quiz_id):
    """Delete a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check ownership
    if not IsQuizOwnerOrAssistant().has_object_permission(request, None, quiz):
        return Response({'detail': 'You do not have permission for this quiz'}, 
                        status=status.HTTP_403_FORBIDDEN)
    
    quiz.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

# Question Views
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_questions(request, quiz_id):
    """List questions for a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user = request.user
    
    # Permission check
    if user.role == 'student':
        try:
            submission = QuizSubmission.objects.get(quiz=quiz, student=user.student_profile)
        except QuizSubmission.DoesNotExist:
            return Response({'detail': 'You have not started this quiz.'}, status=status.HTTP_403_FORBIDDEN)
        
        if not submission.start_time:
            return Response({'detail': 'You must start the quiz before viewing the questions.'}, 
                            status=status.HTTP_403_FORBIDDEN)
        
        # A student cannot view questions after submitting or timing out.
        if submission.is_submitted or submission.is_timed_out:
            return Response({'detail': 'You cannot view questions after submission.'}, status=status.HTTP_403_FORBIDDEN)

        # For students, return questions in the order they were presented when starting
        answers = Answer.objects.filter(
            submission=submission
        ).select_related('question').order_by('order')
        
        # Get the question objects in the correct order
        questions = [answer.question for answer in answers]
        serializer = StudentQuestionSerializer(questions, many=True)
        return Response(serializer.data)
    
    elif user.role in ['teacher', 'assistant', 'admin']:
        if not IsQuizOwnerOrAssistant().has_object_permission(request, None, quiz):
            return Response({'detail': 'You do not have permission for this quiz'}, 
                            status=status.HTTP_403_FORBIDDEN)
        
        # Optimize query to prefetch choices for each question
        questions = quiz.questions.prefetch_related('choices').all()
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)
    
    return Response({'detail': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def question_detail(request, quiz_id, question_id):
    """Get question details"""
    question = get_object_or_404(Question.objects.prefetch_related('choices'), 
                                id=question_id, quiz_id=quiz_id)
    user = request.user
    
    # Permission check
    if user.role == 'student':
        # A student can only view a specific question if they have started the quiz.
        submission = QuizSubmission.objects.filter(
            quiz=question.quiz, 
            student=user.student_profile, 
            start_time__isnull=False
        ).first()
        
        if not submission:
            return Response({'detail': 'You must start the quiz before viewing the questions.'}, 
                            status=status.HTTP_403_FORBIDDEN)
        
        # Verify this question is part of the submission
        if not Answer.objects.filter(submission=submission, question=question).exists():
            return Response({'detail': 'Question not in this quiz'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = StudentQuestionSerializer(question)
        return Response(serializer.data)
    
    elif user.role in ['teacher', 'assistant', 'admin']:
        if not IsQuizOwnerOrAssistant().has_object_permission(request, None, question.quiz):
            return Response({'detail': 'You do not have permission for this quiz'}, 
                            status=status.HTTP_403_FORBIDDEN)
        
        serializer = QuestionSerializer(question)
        return Response(serializer.data)
    
    return Response({'detail': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

# New view to start a quiz and get the authoritative start time
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStudent])
def start_quiz(request, quiz_id):
    """Starts a quiz for a student, creating a submission record and returning the start time."""
    quiz = get_object_or_404(Quiz.objects.select_related('settings'), id=quiz_id)
    student = request.user.student_profile

    # Check availability before starting
    if not CanTakeQuiz().has_permission(request, view=request.parser_context['view']):
        return Response({'detail': 'You cannot take this quiz at this time.'}, 
                        status=status.HTTP_403_FORBIDDEN)

    # Add a defensive check to ensure the quiz has settings.
    if not hasattr(quiz, 'settings'):
        return Response(
            {'detail': f'Configuration error: The quiz "{quiz.title}" is missing its settings. Please contact an administrator.'},
            status=status.HTTP_409_CONFLICT
        )

    with transaction.atomic():
        # Get or create the submission. This is atomic.
        submission, created = QuizSubmission.objects.get_or_create(
            quiz=quiz,
            student=student,
            defaults={'is_submitted': False}
        )

        # If the submission was just created, we need to populate it with ordered answer stubs.
        if created:
            questions = list(quiz.questions.all())

            # Shuffle questions if the quiz setting is 'random'
            if quiz.settings.question_order == 'random':
                random.shuffle(questions)

            # Create placeholder Answer objects with the determined order
            answers_to_create = [
                Answer(submission=submission, question=question, order=index)
                for index, question in enumerate(questions)
            ]
            Answer.objects.bulk_create(answers_to_create)

            # Set the start time only after the setup is complete
            submission.start_time = timezone.now()
            submission.save(update_fields=['start_time'])

    return Response({
        'submission_id': submission.id,
        'start_time': submission.start_time,
    })

# Submission Views
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStudent])
def create_submission(request, quiz_id):
    """Submit quiz answers"""
    student = request.user.student_profile

    # Find any submission for this student/quiz to provide a more specific error.
    try:
        submission = QuizSubmission.objects.select_related('quiz__settings').get(
            quiz_id=quiz_id,
            student=student
        )
    except QuizSubmission.DoesNotExist:
        return Response(
            {'detail': 'You have not started this quiz. Please use the start endpoint first.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Explicitly block any attempt to re-submit a quiz that is already marked as submitted.
    if submission.is_submitted:
        return Response(
            {'detail': 'You are already submitted'},
            status=status.HTTP_409_CONFLICT
        )
        
    # Check 2: Timed out. This is the auto-submission trigger.
    # Any attempt to submit now is invalid because the time is up.
    if submission.is_timed_out:
        # The student's time is up. We should not accept any new answers from this request.
        # We will finalize their submission with a score of 0, but keep is_submitted=False
        # to signify it was an auto-submission.
        with transaction.atomic():
            # We re-fetch and lock the submission to prevent race conditions.
            sub_to_finalize = QuizSubmission.objects.select_for_update().get(pk=submission.pk)
            # Only perform the finalization ONCE by checking if end_time is already set.
            if not sub_to_finalize.end_time:
                # Set the theoretical end time based on the start time and timer.
                try:
                    sub_to_finalize.end_time = sub_to_finalize.start_time + timedelta(minutes=sub_to_finalize.quiz.settings.timer_minutes)
                except OverflowError:
                    # If timer is invalid, just mark the end time as now.
                    sub_to_finalize.end_time = timezone.now()

                sub_to_finalize.score = 0
                sub_to_finalize.save(update_fields=['end_time', 'score'])
        
        # This API call is invalid because the time is up.
        return Response({'detail': 'You are already submitted'}, status=status.HTTP_409_CONFLICT)

    # If we reach here, it's a valid, on-time submission attempt.
    serializer = QuizSubmissionUpdateSerializer(
        data=request.data,
        context={'submission': submission, 'quiz': submission.quiz}
    )

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        # Always update the answers with what the student submitted.
        submission = serializer.update(submission, serializer.validated_data)

        # Finalize the submission by setting the end time and marking it as submitted.
        submission.end_time = timezone.now()
        submission.is_submitted = True

        # If on time, calculate the score based on the submitted answers.
        submission.score = submission.calculate_score()
        submission.save()

    # For on-time submissions, return the normal confirmation.
    return Response(QuizSubmissionConfirmationSerializer(submission).data,
                    status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_submissions(request, quiz_id):
    """
    For Students: List their own quiz submission.
    For Teachers/Assistants: List all assigned students and their submission status for the quiz.
    """
    quiz = get_object_or_404(Quiz.objects.select_related('settings'), id=quiz_id)
    user = request.user

    if user.role == 'student':
        # Original logic for students: fetch their own submission details
        queryset = QuizSubmission.objects.select_related(
            'student__user', 'quiz__settings'
        ).prefetch_related(
            Prefetch('quiz__quizcenter_set', queryset=QuizCenter.objects.select_related('center')),
            Prefetch('answers', queryset=Answer.objects.select_related('question').prefetch_related('selected_choices'))
        )
        submissions = queryset.filter(quiz=quiz, student=user.student_profile)
        serializer = QuizSubmissionSerializer(submissions, many=True, context={'request': request})
        return Response(serializer.data)

    # New logic for Teacher/Assistant
    if not IsQuizOwnerOrAssistant().has_object_permission(request, None, quiz):
        return Response({'detail': 'You do not have permission for this quiz'}, status=status.HTTP_403_FORBIDDEN)


    # Calculate total points for the quiz once to pass to serializer
    total_points = quiz.questions.aggregate(total=Sum('points'))['total'] or 0

    # 1. Get all students assigned to the quiz, sorted by submission start time
    quiz_center_ids = quiz.quizcenter_set.values_list('center_id', flat=True)
    
    # Annotate with submission start_time to allow sorting by it.
    # Newest submissions (non-null start_time) will appear first.
    assigned_students = StudentProfile.objects.filter(
        grade=quiz.grade,
        center_id__in=quiz_center_ids
    ).select_related('user', 'center', 'grade').annotate(
        submission_start_time=Subquery(
            QuizSubmission.objects.filter(
                quiz=quiz,
                student=OuterRef('pk')
            ).values('start_time')[:1]
        )
    ).order_by(F('submission_start_time').desc(nulls_last=True), 'full_name')

    # 2. Get all submissions for this quiz and map them by student ID for efficient lookup
    submissions = QuizSubmission.objects.filter(quiz=quiz)
    submission_map = {sub.student.id: sub for sub in submissions}

    # Create a map of center_id -> QuizCenter for efficient lookup in the serializer
    quiz_center_map = {qc.center_id: qc for qc in quiz.quizcenter_set.all()}

    # 3. Serialize the student list, passing the submission map and total_points in the context
    serializer_context = {
        'submission_map': submission_map,
        'total_points': total_points,
        'quiz_settings': quiz.settings,
        'quiz_center_map': quiz_center_map
    }
    serializer = StudentSubmissionStatusSerializer(assigned_students, many=True, context=serializer_context)
    
    # Serialize quiz settings to include in the response for the teacher/assistant view.
    settings_serializer = QuizSettingsSerializer(quiz.settings)

    return Response({
        'settings': settings_serializer.data,
        'submissions': serializer.data
    })

@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def submission_detail(request, quiz_id, submission_id):
    """
    For Students: Get their own submission details.
    For Teachers/Assistants: Get or Delete a specific submission.
    Deleting a submission allows a student to retake the quiz.
    """
    # Heavy optimization for submission details, prefetching all related data for visibility logic
    queryset = QuizSubmission.objects.select_related(
        'student__user', 'student__center', 'student__grade', 'quiz', 'quiz__settings'
    ).prefetch_related(
        Prefetch('quiz__quizcenter_set', queryset=QuizCenter.objects.select_related('center')),
        Prefetch(
            'answers', 
            queryset=Answer.objects.select_related('question')
                                  .prefetch_related('selected_choices', 'question__choices')
        )
    )
    submission = get_object_or_404(queryset, id=submission_id, quiz_id=quiz_id)
    user = request.user

    # Permission check
    if user.role == 'student' and submission.student != user.student_profile:
        return Response({'detail': 'Not your submission'}, status=status.HTTP_403_FORBIDDEN)

    if user.role in ['teacher', 'assistant']:
        if not IsQuizOwnerOrAssistant().has_object_permission(request, None, submission.quiz):
            return Response({'detail': 'You do not have permission for this quiz'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        # Calculate total points for the quiz to pass to the serializer for display
        total_points = submission.quiz.questions.aggregate(total=Sum('points'))['total'] or 0
        
        serializer_context = {
            'request': request,
            'total_points': total_points
        }
        serializer = QuizSubmissionDetailSerializer(submission, context=serializer_context)
        return Response(serializer.data)

    elif request.method == 'DELETE':
        if user.role not in ['teacher', 'assistant']:
            return Response({'detail': 'You do not have permission to perform this action.'}, status=status.HTTP_403_FORBIDDEN)
        
        submission.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsTeacher | IsAssistant])
def release_all_quiz_results(request, quiz_id):
    """
    Manually release or retract scores and/or answers for ALL submissions of a quiz.
    This is intended for quizzes with 'manual' visibility settings.
    It will only process fields where the corresponding setting is 'manual'.
    Expects a payload like: {"release_score": true, "release_answers": false}.
    """
    quiz = get_object_or_404(Quiz.objects.select_related('settings'), id=quiz_id)

    # Check ownership
    if not IsQuizOwnerOrAssistant().has_object_permission(request, None, quiz):
        return Response({'detail': 'You do not have permission for this quiz'}, status=status.HTTP_403_FORBIDDEN)

    release_score_requested = 'release_score' in request.data
    release_answers_requested = 'release_answers' in request.data

    if not release_score_requested and not release_answers_requested:
        return Response({'detail': 'You must specify to release either scores or answers.'}, 
                        status=status.HTTP_400_BAD_REQUEST)

    update_payload = {}
    action_descs = []

    # Process score release only if setting is manual
    if release_score_requested and quiz.settings.score_visibility == 'manual':
        release_value = bool(request.data.get('release_score'))
        update_payload['is_score_released'] = release_value
        action_status = "released" if release_value else "retracted"
        action_descs.append(f"scores {action_status}")

    # Process answers release only if setting is manual
    if release_answers_requested and quiz.settings.answers_visibility == 'manual':
        release_value = bool(request.data.get('release_answers'))
        update_payload['are_answers_released'] = release_value
        action_status = "released" if release_value else "retracted"
        action_descs.append(f"answers {action_status}")

    # If no valid actions could be taken, return an error
    if not update_payload:
        return Response(
            {'detail': "No action taken. Both score and answer visibility for this quiz are not set to 'manual'."},
            status=status.HTTP_409_CONFLICT
        )

    # Perform the update if there's anything to do
    submissions = QuizSubmission.objects.filter(quiz=quiz, is_submitted=True)
    updated_count = submissions.update(**update_payload)
        
    # Build a descriptive response message
    detail_message = f"Successfully updated {updated_count} submissions: {', '.join(action_descs)}."

    return Response({
        'detail': detail_message,
        'released_scores': update_payload.get('is_score_released'),
        'released_answers': update_payload.get('are_answers_released'),
    }, status=status.HTTP_200_OK)

# Additional helper view
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStudent])
def check_quiz_availability(request, quiz_id):
    """Check if a quiz is available to a student"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    student = request.user.student_profile
    
    # Check grade
    if quiz.grade != student.grade:
        return Response({
            'available': False,
            'reason': 'Not available for your grade'
        })
    
    # Check center
    try:
        quiz_center = QuizCenter.objects.get(quiz=quiz, center=student.center)
    except QuizCenter.DoesNotExist:
        return Response({
            'available': False,
            'reason': 'Not available for your center'
        })
    
    # Check timing
    now = timezone.now()
    local_open_date = timezone.localtime(quiz_center.open_date)
    local_close_date = timezone.localtime(quiz_center.close_date)

    if now < quiz_center.open_date:
        return Response({
            'available': False,
            'reason': f'Quiz opens at {local_open_date.strftime("%-d %B, %I:%M %p")}'
        })
    
    if now > quiz_center.close_date:
        return Response({
            'available': False,
            'reason': f'Quiz closed at {local_close_date.strftime("%-d %B, %I:%M %p")}'
        })
    
    # Check existing submission
    if QuizSubmission.objects.filter(quiz=quiz, student=student, is_submitted=True).exists():
        return Response({
            'available': False,
            'reason': 'You already submitted this quiz'
        })
    
    return Response({
        'available': True,
        'open_date': quiz_center.open_date,
        'close_date': quiz_center.close_date
    })