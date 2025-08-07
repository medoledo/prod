#session/views.py

from itertools import groupby
from operator import itemgetter

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from .models import Session, SessionAttendance, SessionTestScore, SessionHomework
from .serializers import (
    SessionSerializer, 
    SessionAttendanceSerializer,
    SessionTestScoreSerializer,
    SessionHomeworkSerializer,
    SessionMaxScoreSerializer
)
from .permissions import CanManageSession, get_teacher
from accounts.permissions import IsTeacher, IsAssistant
from accounts.views import IsTeacherOrAssistant
from django.shortcuts import get_object_or_404
from accounts.models import StudentProfile
from django.db import transaction  # Added for atomic transactions
from accounts.models import Center, Grade
from django.db.models import Count, Sum, Case, When, IntegerField, FloatField, Q, Avg
from django.db import models
from rest_framework.exceptions import PermissionDenied

def _check_session_permission(request, session):
    """
    Helper to centralize checking object-level permissions for a session.
    This avoids repeating the same permission check logic in multiple views
    and uses DRF's standard exception handling.
    """
    permission_checker = CanManageSession()
    if not permission_checker.has_object_permission(request, view=None, obj=session):
        raise PermissionDenied('You do not have permission for this session.')

@api_view(['GET'])
@permission_classes([IsTeacherOrAssistant])
def list_sessions(request):
    teacher = get_teacher(request.user)
    sessions = Session.objects.filter(teacher=teacher).select_related('grade', 'center')

    # Add date range filtering
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    if start_date and end_date:
        sessions = sessions.filter(date__range=[start_date, end_date])
    elif start_date:
        sessions = sessions.filter(date__gte=start_date)
    elif end_date:
        sessions = sessions.filter(date__lte=end_date)

    serializer = SessionSerializer(sessions, many=True, context={'request': request})
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsTeacherOrAssistant])
def create_session(request):
    serializer = SessionSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def session_detail(request, pk):
    session = get_object_or_404(Session, pk=pk)
    _check_session_permission(request, session)

    if request.method == 'GET':
        serializer = SessionSerializer(session, context={'request': request})
        return Response(serializer.data)

    elif request.method == 'PUT':
        # Prevent changing teacher, grade, or center
        if any(field in request.data for field in ['teacher', 'grade', 'center']):
            return Response(
                {'detail': 'Cannot change teacher, grade, or center of a session'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = SessionSerializer(
            session,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        session.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['PUT'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def set_session_max_score(request, pk):
    session = get_object_or_404(Session, pk=pk)
    _check_session_permission(request, session)

    if not session.has_test:
        return Response(
            {'detail': 'Cannot set max score for a session without a test.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Prevent setting max_score lower than an existing score
    if 'test_max_score' in request.data:
        new_max_score = request.data['test_max_score']
        if new_max_score:
            max_existing_score = session.test_scores.aggregate(max_score=models.Max('score'))['max_score']
            if max_existing_score is not None and float(new_max_score) < max_existing_score:
                return Response(
                    {'detail': f"Cannot set max score to {new_max_score}. An existing score of {max_existing_score} is higher."},
                    status=status.HTTP_400_BAD_REQUEST
                )

    serializer = SessionMaxScoreSerializer(session, data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(SessionSerializer(session, context={'request': request}).data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def session_attendance_list(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    _check_session_permission(request, session)
    attendance = SessionAttendance.objects.filter(session=session)
    serializer = SessionAttendanceSerializer(attendance, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def create_session_attendance(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    _check_session_permission(request, session)

    # Expecting a list of attendance records
    if not isinstance(request.data, list):
        return Response(
            {'detail': 'Expected a list of attendance records'},
            status=status.HTTP_400_BAD_REQUEST
        )

    success_records = []
    failed_records = []
    with transaction.atomic():
        for record_data in request.data:
            serializer = SessionAttendanceSerializer(data=record_data, context={'request': request, 'session': session})
            if serializer.is_valid():
                student = serializer.validated_data['student']
                attended = serializer.validated_data['attended']
                obj, created = SessionAttendance.objects.update_or_create(
                    session=session, student=student, defaults={'attended': attended}
                )
                success_records.append(SessionAttendanceSerializer(obj).data)
            else:
                failed_records.append({
                    'input': record_data,
                    'errors': serializer.errors
                })

    return Response({
        'detail': f'Processed {len(success_records)} records successfully and {len(failed_records)} failed.',
        'success': success_records,
        'errors': failed_records
    }, status=status.HTTP_207_MULTI_STATUS if failed_records else status.HTTP_201_CREATED)

@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def session_attendance_detail(request, session_id, student_id):
    session = get_object_or_404(Session, pk=session_id)
    _check_session_permission(request, session)
    # Further permission checks can be added here if needed
    attendance_record = get_object_or_404(SessionAttendance, session=session, student_id=student_id)

    if request.method == 'GET':
        serializer = SessionAttendanceSerializer(attendance_record)
        return Response(serializer.data)
    elif request.method in ['PUT', 'PATCH']:
        serializer = SessionAttendanceSerializer(attendance_record, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'DELETE':
        attendance_record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def session_scores_list(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    _check_session_permission(request, session)
    # Optimized query to prevent N+1 issues from student and session lookups in serializer
    scores = SessionTestScore.objects.filter(session=session).select_related(
        'student', 'student__center', 'session'
    )
    serializer = SessionTestScoreSerializer(scores, many=True, context={'request': request})
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def create_session_score(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    _check_session_permission(request, session)

    if not session.has_test:
        return Response(
            {'detail': 'This session is not marked as having a test.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if session.test_max_score is None:
        return Response(
            {'detail': "The test's maximum score has not been set for this session yet."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Expecting a list of score records
    if not isinstance(request.data, list):
        return Response(
            {'detail': 'Expected a list of test score records'},
            status=status.HTTP_400_BAD_REQUEST
        )

    success_records = []
    failed_records = []
    with transaction.atomic():
        for record_data in request.data:
            serializer = SessionTestScoreSerializer(data=record_data, context={'request': request, 'session': session})
            if serializer.is_valid():
                student = serializer.validated_data['student']
                score_data = {
                    'score': serializer.validated_data['score'],
                    'notes': serializer.validated_data.get('notes', '')
                }
                obj, created = SessionTestScore.objects.update_or_create(
                    session=session, student=student, defaults=score_data
                )
                success_records.append(SessionTestScoreSerializer(obj).data)
            else:
                failed_records.append({
                    'input': record_data,
                    'errors': serializer.errors
                })

    return Response({
        'detail': f'Processed {len(success_records)} records successfully and {len(failed_records)} failed.',
        'success': success_records,
        'errors': failed_records
    }, status=status.HTTP_207_MULTI_STATUS if failed_records else status.HTTP_201_CREATED)

@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def session_score_detail(request, session_id, student_id):
    session = get_object_or_404(Session, pk=session_id)
    _check_session_permission(request, session)
    
    score_record = get_object_or_404(SessionTestScore, session=session, student_id=student_id)

    if request.method == 'GET':
        serializer = SessionTestScoreSerializer(score_record)
        return Response(serializer.data)

    elif request.method in ['PUT', 'PATCH']:
        # Pass session context for validation within the serializer
        serializer = SessionTestScoreSerializer(score_record, data=request.data, partial=True, context={'request': request, 'session': session})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        score_record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
@api_view(['GET'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def session_homework_list(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    _check_session_permission(request, session)
    homework = SessionHomework.objects.filter(session=session)
    serializer = SessionHomeworkSerializer(homework, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def create_session_homework(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    _check_session_permission(request, session)

    # Expecting a list of homework records
    if not isinstance(request.data, list):
        return Response(
            {'detail': 'Expected a list of homework records'},
            status=status.HTTP_400_BAD_REQUEST
        )

    success_records = []
    failed_records = []
    with transaction.atomic():
        for record_data in request.data:
            serializer = SessionHomeworkSerializer(data=record_data, context={'request': request, 'session': session})
            if serializer.is_valid():
                student = serializer.validated_data['student']
                homework_data = {
                    'completed': serializer.validated_data['completed'],
                    'notes': serializer.validated_data.get('notes', '')
                }
                obj, created = SessionHomework.objects.update_or_create(
                    session=session, student=student, defaults=homework_data
                )
                success_records.append(SessionHomeworkSerializer(obj).data)
            else:
                failed_records.append({
                    'input': record_data,
                    'errors': serializer.errors
                })

    return Response({
        'detail': f'Processed {len(success_records)} records successfully and {len(failed_records)} failed.',
        'success': success_records,
        'errors': failed_records
    }, status=status.HTTP_207_MULTI_STATUS if failed_records else status.HTTP_201_CREATED)

# Placeholder for session_homework_detail view if needed
# Similar implementation to session_attendance_detail






@api_view(['GET'])
@permission_classes([IsTeacherOrAssistant, CanManageSession])
def session_stats(request, pk):
    session = get_object_or_404(Session, pk=pk)
    _check_session_permission(request, session)

    # Get total expected students for the session's center/grade
    expected_students_count = StudentProfile.objects.filter(
        center=session.center,
        grade=session.grade,
        is_approved=True
    ).count()

    # Use a single query with conditional aggregation for all attendance stats
    attendance_stats = SessionAttendance.objects.filter(session=session).aggregate(
        total_present=Count('pk', filter=Q(attended=True)),
        present_same_center=Count('pk', filter=Q(attended=True, student__center=session.center)),
        present_other_center=Count('pk', filter=Q(attended=True) & ~Q(student__center=session.center)),
        marked_absent_same_center=Count('pk', filter=Q(attended=False, student__center=session.center))
    )

    # Calculate unmarked students from the session's center
    marked_student_ids = SessionAttendance.objects.filter(
        session=session, student__center=session.center
    ).values_list('student_id', flat=True)
    unmarked_count = StudentProfile.objects.filter(
        center=session.center, grade=session.grade, is_approved=True
    ).exclude(id__in=marked_student_ids).count()

    total_absent = attendance_stats['marked_absent_same_center'] + unmarked_count

    return Response({
        'session_id': session.id,
        'date': session.date,
        'title': session.title,
        'center': session.center.name,
        'grade': session.grade.name,
        'total_present': attendance_stats['total_present'],
        'total_absent': total_absent,
        'present_same_center': attendance_stats['present_same_center'],
        'present_other_center': attendance_stats['present_other_center'],
        'expected_attendance_same_center': expected_students_count
    }, status=status.HTTP_200_OK)



@api_view(['GET'])
@permission_classes([IsTeacherOrAssistant])
def center_attendance_stats(request):
    teacher = get_teacher(request.user)

    # This single query calculates the average attendance for each grade within each center.
    # It works by treating 'present' as 100 and 'absent' as 0, then averaging the result.
    # This is vastly more performant than nested loops.
    stats_query = Session.objects.filter(teacher=teacher).values(
        'center__id', 'center__name', 'grade__id', 'grade__name'
    ).annotate(
        attendance_percentage=Avg(
            Case(
                When(attendance_records__attended=True, then=100.0),
                default=0.0,
                output_field=FloatField()
            )
        )
    ).order_by('center__name', 'grade__name')

    center_stats = []
    # Group the flat list of results by center to create the nested structure.
    for center_key, grades_group in groupby(stats_query, key=lambda x: (x['center__id'], x['center__name'])):
        center_id, center_name = center_key
        grades_data = []
        for grade in grades_group:
            # Only add grades that have had sessions (and thus have stats)
            if grade['attendance_percentage'] is not None:
                grades_data.append({
                    'grade_id': grade['grade__id'],
                    'grade_name': grade['grade__name'],
                    'attendance_percentage': round(grade['attendance_percentage'], 2)
                })
        
        if not grades_data:
            continue
            
        center_stats.append({
            'center_id': center_id,
            'center_name': center_name,
            'grades': grades_data
        })

    return Response({
        'teacher_id': teacher.id,
        'teacher_name': teacher.full_name,
        'centers': center_stats
    }, status=status.HTTP_200_OK)