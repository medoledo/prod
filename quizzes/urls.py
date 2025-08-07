# quizzes/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Quiz Management Endpoints
    path('quizzes/create/', views.create_quiz, name='create_quiz'),
    path('quizzes/', views.list_quizzes, name='list_quizzes'),
    path('quizzes/<int:quiz_id>/', views.quiz_detail_or_update, name='quiz_detail_or_update'),
    path('quizzes/<int:quiz_id>/delete/', views.delete_quiz, name='delete_quiz'),
    path('quizzes/<int:quiz_id>/release-all/', views.release_all_quiz_results, name='release_all_quiz_results'),

    # Question Management Endpoints
    path('quizzes/<int:quiz_id>/questions/', views.list_questions, name='list_questions'),

    # Quiz Submission Endpoints
    path('quizzes/<int:quiz_id>/start/', views.start_quiz, name='start_quiz'),
    path('quizzes/<int:quiz_id>/submissions/create/', views.create_submission, name='create_submission'),
    path('quizzes/<int:quiz_id>/submissions/', views.list_submissions, name='list_submissions'),
    path('quizzes/<int:quiz_id>/submissions/<int:submission_id>/', views.submission_detail, name='submission_detail'),

    # Quiz Availability Check
    path('quizzes/<int:quiz_id>/availability/', views.check_quiz_availability, name='check_quiz_availability'),
]