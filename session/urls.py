#session/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Session endpoints
    path('sessions/', views.list_sessions, name='list_sessions'),
    path('sessions/create/', views.create_session, name='create_session'),
    path('sessions/<int:pk>/', views.session_detail, name='session_detail'),
    path('sessions/<int:pk>/set-max-score/', views.set_session_max_score, name='set_session_max_score'),

    # Attendance endpoints
    path('sessions/<int:session_id>/attendance/',
         views.session_attendance_list, name='session_attendance_list'),
    path('sessions/<int:session_id>/attendance/create/',
         views.create_session_attendance, name='create_session_attendance'),
    path('sessions/<int:session_id>/attendance/<int:student_id>/',
         views.session_attendance_detail, name='session_attendance_detail'),

    # Test score endpoints
    path('sessions/<int:session_id>/scores/',
         views.session_scores_list, name='session_scores_list'),
    path('sessions/<int:session_id>/scores/create/',
         views.create_session_score, name='create_session_score'),
    path('sessions/<int:session_id>/scores/<int:student_id>/',
         views.session_score_detail, name='session_score_detail'),

    # Homework endpoints
    path('sessions/<int:session_id>/homework/',
         views.session_homework_list, name='session_homework_list'),
    path('sessions/<int:session_id>/homework/create/',
         views.create_session_homework, name='create_session_homework'),


    # session detailed attendance endpoints
    path('sessions/<int:pk>/stats/', views.session_stats, name='session_stats'),


    # Average center attendance endpoints
    path('sessions/center-attendance/', views.center_attendance_stats, name='center_attendance_stats'),

]