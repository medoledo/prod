# studymaterials/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import StudyWeek, StudyMaterial
from .serializers import StudyWeekSerializer, StudyMaterialSerializer
from django.shortcuts import get_object_or_404
from .permissions import IsTeacherOrAssistant, CanAccessStudyWeek, CanAccessStudyMaterial

def get_accessible_weeks(user):
    """Returns a queryset of StudyWeek objects accessible by the given user."""
    if user.role == 'teacher':
        return StudyWeek.objects.filter(teacher=user.teacher_profile)
    elif user.role == 'assistant':
        return StudyWeek.objects.filter(teacher=user.assistant_profile.teacher)
    elif user.role == 'student':
        student = user.student_profile
        return StudyWeek.objects.filter(grade=student.grade, centers=student.center)
    return StudyWeek.objects.none()

def get_accessible_materials(user):
    """Returns a queryset of StudyMaterial objects accessible by the given user."""
    if user.role == 'teacher':
        return StudyMaterial.objects.filter(teacher=user.teacher_profile)
    elif user.role == 'assistant':
        return StudyMaterial.objects.filter(teacher=user.assistant_profile.teacher)
    elif user.role == 'student':
        student = user.student_profile
        return StudyMaterial.objects.filter(week__grade=student.grade, week__centers=student.center)
    return StudyMaterial.objects.none()

# Study Weeks Views
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def week_list(request):
    """List study weeks accessible to the user"""
    # Fetch weeks ordered by creation date (ascending = oldest first)
    weeks = get_accessible_weeks(request.user) \
        .select_related('grade') \
        .prefetch_related('centers') \
        .order_by('date_created')  # Add ordering here

    # Optional date filtering
    created_after = request.query_params.get('created_after')
    if created_after:
        weeks = weeks.filter(date_created__gte=created_after)

    serializer = StudyWeekSerializer(weeks, many=True, context={'request': request})
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsTeacherOrAssistant])
def week_create(request):
    """Create a new study week"""
    serializer = StudyWeekSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def week_detail(request, pk):
    """Retrieve, update or delete a study week"""
    week = get_object_or_404(StudyWeek, pk=pk)

    # Check object-level permissions manually
    permission = CanAccessStudyWeek()
    if not permission.has_object_permission(request, None, week):
        return Response(
            {'detail': 'You do not have permission to access this resource'},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == 'GET':
        serializer = StudyWeekSerializer(week)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = StudyWeekSerializer(
            week,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        week.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# Study Materials Views
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def material_list(request):
    """List study materials accessible to the user"""
    # Fetch materials ordered by creation date (oldest first) and ID
    materials = get_accessible_materials(request.user) \
        .select_related('week', 'teacher') \
        .order_by('date_created', 'id')  # Add ordering here

    # Optional date filtering
    created_after = request.query_params.get('created_after')
    if created_after:
        materials = materials.filter(date_created__gte=created_after)

    serializer = StudyMaterialSerializer(materials, many=True, context={'request': request})
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsTeacherOrAssistant])
def material_create(request):
    """Create a new study material"""
    serializer = StudyMaterialSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def material_detail(request, pk):
    """Retrieve, update or delete a study material"""
    material = get_object_or_404(StudyMaterial, pk=pk)

    # Check object-level permissions manually
    permission = CanAccessStudyMaterial()
    if not permission.has_object_permission(request, None, material):
        return Response(
            {'detail': 'You do not have permission to access this resource'},
            status=status.HTTP_403_FORBIDDEN
        )

    if request.method == 'GET':
        serializer = StudyMaterialSerializer(material, context={'request': request})
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = StudyMaterialSerializer(
            material,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        material.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)