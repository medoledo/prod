#accounts/urls.py

from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from .views import CustomTokenObtainPairView , PublicKeyView , CustomTokenRefreshView

urlpatterns = [
    # Authentication Endpoints
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('public-key/', PublicKeyView.as_view(), name='public-key'),

    # Dashboard Endpoints
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('dashboard/student/', views.student_dashboard, name='student_dashboard'),
    path('dashboard/assistant/', views.assistant_dashboard, name='assistant_dashboard'),

    # Student Management
    path('students/', views.list_students, name='list_students'),
    path('students/create/', views.create_student, name='create_student'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    path('students/approve/', views.approve_students, name='approve_students'),


    # Teacher Management
    path('teachers/', views.list_teachers, name='list_teachers'),
    path('teachers/create/', views.create_teacher_profile, name='create_teacher'),
    path('teachers/me/', views.my_teacher_profile, name='my_teacher_profile'),
    path('teachers/<int:pk>/', views.teacher_detail, name='teacher_detail'),
    path('teachers/<int:teacher_id>/students/', views.teacher_students, name='teacher_students'),
    path('teachers/<int:teacher_id>/students/active/', views.teacher_active_students, name='teacher_active_students'),
    path('teachers/<int:teacher_id>/students/inactive/', views.teacher_inactive_students, name='teacher_inactive_students'),

    # Replace existing assistant URLs with these
    path('assistants/', views.assistant_list, name='assistant_list'),
    path('assistants/create/', views.create_assistant, name='create_assistant'),
    path('assistants/<int:pk>/', views.assistant_detail, name='assistant_detail'),


    # Center Management
    path('centers/create/', views.create_center, name='create_center'),
    path('centers/', views.list_centers, name='list_centers'),


    path('grades/', views.grade_list, name='grade-list'),
    path('subjects/', views.subject_list, name='subject-list'),


    path('students/export/', views.export_students_to_excel, name='export_students'),


]