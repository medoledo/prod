#session/permissions.py

from rest_framework.permissions import BasePermission

def get_teacher(user):
    """Get teacher profile from user (handles assistants)"""
    if user.role == 'teacher' and hasattr(user, 'teacher_profile'):
        return user.teacher_profile
    if user.role == 'assistant' and hasattr(user, 'assistant_profile'):
        return user.assistant_profile.teacher
    return None

class CanManageSession(BasePermission):
    """Teachers/assistants can manage their own sessions"""
    def has_object_permission(self, request, view, obj):
        teacher = get_teacher(request.user)
        return teacher == obj.teacher

class CanAccessSession(BasePermission):
    """Students can only view sessions for their grade/center"""
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'student':
            student = request.user.student_profile
            return (student.grade == obj.grade and 
                    student.center == obj.center)
        return True