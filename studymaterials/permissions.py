#studymaterials/permissions.py


from rest_framework.permissions import BasePermission, SAFE_METHODS

def get_teacher_profile(user):
    """Helper to get the teacher profile for a teacher or their assistant."""
    if user.role == 'teacher' and hasattr(user, 'teacher_profile'):
        return user.teacher_profile
    elif user.role == 'assistant' and hasattr(user, 'assistant_profile'):
        # Assistants act on behalf of their teacher
        return user.assistant_profile.teacher
    return None

class IsTeacherOrAssistant(BasePermission):
    """
    Allows access only to 'teacher' or 'assistant' users.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['teacher', 'assistant']

class CanAccessStudyWeek(BasePermission):
    """
    Object-level permission for StudyWeek.
    - Teachers/Assistants can do anything to weeks they own.
    - Students can only view weeks assigned to their grade and center.
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role in ['teacher', 'assistant']:
            teacher = get_teacher_profile(user)
            # Allow if the teacher of the week is the user's teacher
            return obj.teacher == teacher

        elif user.role == 'student' and hasattr(user, 'student_profile'):
            student = user.student_profile
            # Students can only perform safe actions (GET, HEAD, OPTIONS)
            if request.method in SAFE_METHODS:
                return obj.grade == student.grade and obj.centers.filter(id=student.center.id).exists()
            return False # Students cannot modify weeks

        return False

class CanAccessStudyMaterial(BasePermission):
    """
    Object-level permission for StudyMaterial.
    - Teachers/Assistants can do anything to materials they own.
    - Students can only view materials if they have access to the parent week.
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role in ['teacher', 'assistant']:
            teacher = get_teacher_profile(user)
            return obj.teacher == teacher

        elif user.role == 'student' and hasattr(user, 'student_profile'):
            student = user.student_profile
            week = obj.week
            # Students can only perform safe actions (GET, HEAD, OPTIONS)
            if request.method in SAFE_METHODS:
                return week.grade == student.grade and week.centers.filter(id=student.center.id).exists()
            return False # Students cannot modify materials

        return False