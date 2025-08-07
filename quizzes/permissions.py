#quizzes/permissions.py

from rest_framework.permissions import BasePermission
from .models import Quiz, QuizCenter
from django.utils import timezone

class IsQuizOwnerOrAssistant(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        
        # If the object is a Quiz
        if isinstance(obj, Quiz):
            teacher = obj.teacher
        # If the object is a QuizSubmission, then get the quiz's teacher
        elif hasattr(obj, 'quiz'):
            teacher = obj.quiz.teacher
        else:
            return False
        
        if request.user.role == 'teacher' and request.user.teacher_profile == teacher:
            return True
        
        if request.user.role == 'assistant' and hasattr(request.user, 'assistant_profile'):
            return request.user.assistant_profile.teacher == teacher
        
        return False

class CanTakeQuiz(BasePermission):
    def has_permission(self, request, view):
        if request.user.role != 'student':
            return False
        
        # Check if the quiz exists and is assigned to the student's center and grade
        quiz_id = view.kwargs.get('quiz_id')
        student = request.user.student_profile
        
        try:
            quiz = Quiz.objects.get(id=quiz_id)
            quiz_center = QuizCenter.objects.get(quiz=quiz, center=student.center)
            
            # Check if the quiz is open for the student's center
            now = timezone.now()
            if now < quiz_center.open_date or now > quiz_center.close_date:
                return False
            
            # Check if the student's grade matches the quiz's assigned grade
            if student.grade != quiz.grade:  # Changed to single grade comparison
                return False
            
            return True
        except (Quiz.DoesNotExist, QuizCenter.DoesNotExist):
            return False