#session/serializers.py

from rest_framework import serializers
from .models import Session, SessionAttendance, SessionTestScore, SessionHomework
from accounts.serializers import StudentProfileSerializer, GradeSerializer, CenterSerializer
from accounts.models import Center, Grade, StudentProfile
from django.core.exceptions import ValidationError as DjangoValidationError

class SessionSerializer(serializers.ModelSerializer):
    grade = GradeSerializer(read_only=True)
    center = CenterSerializer(read_only=True)
    grade_id = serializers.PrimaryKeyRelatedField(
        queryset=Grade.objects.all(), 
        source='grade',
        write_only=True
    )
    center_id = serializers.PrimaryKeyRelatedField(
        queryset=Center.objects.all(), 
        source='center',
        write_only=True
    )
    teacher_name = serializers.CharField(
        source='teacher.full_name', 
        read_only=True
    )
    students = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = [
            'id', 'date', 'title', 'notes', 'grade', 'center', 'grade_id',
            'center_id', 'teacher_name', 'created_at', 'students', 'has_homework',
            'has_test', 'test_max_score'
        ]
        read_only_fields = ['id', 'created_at', 'teacher_name', 'students', 'test_max_score']

    def get_students(self, obj):
        """
        Get ONLY students who attended this session (attended=True).
        Returns student details without attendance status since it's always True.
        """
        attendance_records = SessionAttendance.objects.filter(
            session=obj,
            attended=True  # Filter for attended students only
        ).select_related('student', 'student__center')
        
        return [{
            'id': record.student.id,
            'full_name': record.student.full_name,
            'student_id': record.student.student_id,
            'center_id': record.student.center.id,
            'center_name': record.student.center.name,
            'is_approved': record.student.is_approved,
            # Removed 'attended' field since it's always True
        } for record in attendance_records]

    def create(self, validated_data):
        # Set teacher from request user
        user = self.context['request'].user
        if user.role == 'teacher':
            teacher = user.teacher_profile
        elif user.role == 'assistant':
            teacher = user.assistant_profile.teacher
        else:
            raise serializers.ValidationError("Invalid user role for session creation")
        
        # Validate teacher owns the center
        center = validated_data['center']
        if center.teacher != teacher:
            raise serializers.ValidationError(
                "Center does not belong to your teacher profile"
            )
        
        # Validate teacher teaches this grade
        grade = validated_data['grade']
        if not teacher.grades.filter(id=grade.id).exists():
            raise serializers.ValidationError(
                "Teacher is not assigned to this grade"
            )
        
        validated_data['teacher'] = teacher
        return super().create(validated_data)

class SessionMaxScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = ['test_max_score']

    def validate_test_max_score(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Max score must be a positive number.")
        return value

class SessionAttendanceSerializer(serializers.ModelSerializer):
    student = StudentProfileSerializer(read_only=True)
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=StudentProfile.objects.none(),  # Start empty - will be set dynamically
        source='student',
        write_only=True
    )

    class Meta:
        model = SessionAttendance
        fields = ['id', 'session', 'student', 'student_id', 'attended']
        read_only_fields = ['id', 'session']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically set student queryset based on session context
        if 'context' in kwargs and 'session' in kwargs['context']:
            session = kwargs['context']['session']
            teacher = session.teacher
            centers = Center.objects.filter(teacher=teacher)
            self.fields['student_id'].queryset = StudentProfile.objects.filter(
                grade=session.grade,
                center__in=centers
            )

class SessionTestScoreSerializer(serializers.ModelSerializer):
    student = StudentProfileSerializer(read_only=True)
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=StudentProfile.objects.none(),  # Start empty - will be set dynamically
        source='student',
        write_only=True
    )
    percentage = serializers.SerializerMethodField()
    max_score = serializers.DecimalField(source='session.test_max_score', read_only=True, max_digits=5, decimal_places=2)

    class Meta:
        model = SessionTestScore
        fields = [
            'id', 'session', 'student', 'student_id', 'score', 'max_score', 'percentage',
            'notes'
        ]
        read_only_fields = ['id', 'session', 'percentage', 'max_score']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically set student queryset based on session context
        if 'context' in kwargs and 'session' in kwargs['context']:
            session = kwargs['context']['session']
            teacher = session.teacher
            centers = Center.objects.filter(teacher=teacher)
            self.fields['student_id'].queryset = StudentProfile.objects.filter(
                grade=session.grade,
                center__in=centers
            )

    def get_percentage(self, obj):
        if obj.session.test_max_score and obj.session.test_max_score > 0:
            return round((obj.score / obj.session.test_max_score) * 100, 2)
        return 0

    def validate(self, attrs):
        session = self.context.get('session')
        if not session:
            raise serializers.ValidationError("Session context is required.")

        if not session.has_test:
            raise serializers.ValidationError("This session is not marked as having a test.")

        if session.test_max_score is None:
            raise serializers.ValidationError(
                "The maximum score for this session's test has not been set."
            )

        # Validate score doesn't exceed max
        if attrs['score'] > session.test_max_score:
            raise serializers.ValidationError(
                f"Score ({attrs['score']}) exceeds the session's maximum value ({session.test_max_score})."
            )
        return attrs

class SessionHomeworkSerializer(serializers.ModelSerializer):
    student = StudentProfileSerializer(read_only=True)
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=StudentProfile.objects.none(),  # Start empty - will be set dynamically
        source='student',
        write_only=True
    )

    class Meta:
        model = SessionHomework
        fields = ['id', 'session', 'student', 'student_id', 'completed', 'notes']
        read_only_fields = ['id', 'session']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically set student queryset based on session context
        if 'context' in kwargs and 'session' in kwargs['context']:
            session = kwargs['context']['session']
            teacher = session.teacher
            centers = Center.objects.filter(teacher=teacher)
            self.fields['student_id'].queryset = StudentProfile.objects.filter(
                grade=session.grade,
                center__in=centers
            )