# accounts/serializers.py

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.exceptions import TokenError

import random
import string

from .models import (
    TeacherProfile, StudentProfile,
    Center, Grade, Subject , AssistantProfile
)

User = get_user_model()


# ------------------------------------------------------------------------------
# User Serializer
# ------------------------------------------------------------------------------
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    session_token = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'password', 'session_token']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user


# ------------------------------------------------------------------------------
# Teacher Profile Serializer
# ------------------------------------------------------------------------------
class TeacherProfileSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source='user.username', read_only=True)
    grades = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Grade.objects.all(),
        required=False
    )
    students = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = [
            'id', 'full_name', 'phone_number', 'gender', 'brand',
            'user', 'subject', 'grades', 'students'
        ]
        read_only_fields = ['user']

    def get_students(self, obj):
        qs = obj.students.all()
        return {
            'total_students': qs.count(),
            'active_students': qs.filter(is_approved=True).count(),
            'inactive_students': qs.filter(is_approved=False).count(),
            'students_data': StudentProfileSerializer(qs, many=True).data
        }

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # nest subject
        rep['subject'] = (
            {'id': instance.subject.id, 'name': instance.subject.name}
            if instance.subject else None
        )
        return rep

    def create(self, validated_data):
        grades = validated_data.pop('grades', [])
        teacher = TeacherProfile.objects.create(**validated_data)
        teacher.grades.set(grades)
        return teacher

    def update(self, instance, validated_data):
        grades = validated_data.pop('grades', None)
        if grades is not None:
            instance.grades.set(grades)
        return super().update(instance, validated_data)


# ------------------------------------------------------------------------------
# Student Profile Serializer
# ------------------------------------------------------------------------------
class StudentProfileSerializer(serializers.ModelSerializer):
    # expose username on read, allow changing on write
    username = serializers.CharField(
        source='user.username',
        required=False,
        allow_blank=False
    )
    # allow password change but never return it
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=8
    )

    student_id = serializers.CharField(read_only=True)
    grade = serializers.PrimaryKeyRelatedField(
        queryset=Grade.objects.all(),
        required=True,
        error_messages={'required': 'Grade field is required'}
    )
    center = serializers.PrimaryKeyRelatedField(
        queryset=Center.objects.all(),
        required=True,
        error_messages={'required': 'Center field is required'}
    )
    added_by = serializers.CharField(read_only=True)

    class Meta:
        model = StudentProfile
        fields = [
            'id', 'student_id', 'grade', 'center', 'added_by',
            'full_name', 'phone_number', 'parent_number', 'gender',
            'is_approved', 'user', 'teacher',
            'username', 'password'
        ]
        read_only_fields = [
            'id', 'student_id', 'user', 'teacher',
            'is_approved', 'added_by'
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['grade'] = {'id': instance.grade.id, 'name': instance.grade.name}
        rep['center'] = {'id': instance.center.id, 'name': instance.center.name}
        rep['teacher'] = {
            'id': instance.teacher.id,
            'full_name': instance.teacher.full_name
        }
        rep['username'] = instance.user.username
        return rep

    def validate_center(self, value):
        teacher = self.context.get('teacher')
        if value.teacher != teacher:
            raise serializers.ValidationError(
                "Center does not belong to the specified teacher"
            )
        return value

    def validate(self, data):
        phone = data.get('phone_number', '')
        parent = data.get('parent_number', '')
        if phone and len(phone) != 11:
            raise serializers.ValidationError(
                {'phone_number': 'Phone number must be 11 digits'}
            )
        if parent and len(parent) != 11:
            raise serializers.ValidationError(
                {'parent_number': 'Parent phone number must be 11 digits'}
            )
        return data

    def create(self, validated_data):
        request = self.context['request']
        user = request.user

        if user.role == 'teacher' and hasattr(user, 'teacher_profile'):
            validated_data['added_by'] = user.teacher_profile.full_name
        elif user.role == 'assistant' and hasattr(user, 'assistant_profile'):
            validated_data['added_by'] = user.assistant_profile.full_name
        else:
            validated_data['added_by'] = user.username

        validated_data.pop('student_id', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # handle username
        user_data = validated_data.pop('user', {})
        new_username = user_data.get('username')
        if new_username:
            instance.user.username = new_username

        # handle password
        new_password = validated_data.pop('password', None)
        if new_password:
            instance.user.set_password(new_password)

        if new_username or new_password:
            instance.user.save()

        return super().update(instance, validated_data)


# ------------------------------------------------------------------------------
# Center, Grade, Subject Serializers
# ------------------------------------------------------------------------------
class CenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Center
        fields = ['id', 'name', 'teacher']


class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grade
        fields = ['id', 'name']


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name']


# ------------------------------------------------------------------------------
# Custom JWT Token Serializers
# ------------------------------------------------------------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = user.role
        token['session_token'] = user.session_token

        token['full_name'] = user.get_full_name()
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        # Check if the user is a student and if their profile is approved
        if user.role == 'student':
            try:
                if not user.student_profile.is_approved:
                    raise serializers.ValidationError(
                        'Your account is pending approval. Please contact the administration.'
                    )
            except StudentProfile.DoesNotExist:
                # This is a data integrity issue, but good to handle gracefully.
                raise serializers.ValidationError(
                    'Incomplete student profile. Please contact support.'
                )

        # rotate session_token
        new_token = ''.join(random.choices(string.digits, k=10))
        user.session_token = new_token
        user.save()

        refresh = self.get_token(user)
        data.update({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'username': user.username,
            'full_name': user.get_full_name(),
            'role': user.role,
            'session_token': new_token,
            'teacher_brand': user.get_associated_teacher_brand()
        })
        return data


class CustomTokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        refresh_token = attrs['refresh']
        try:
            refresh = RefreshToken(refresh_token)
            user_id = refresh.payload.get('user_id')
            token_session = refresh.payload.get('session_token')

            user = User.objects.get(id=user_id)
            if token_session != user.session_token:
                raise serializers.ValidationError(
                    'Session expired. Please log in again.'
                )

            full_name = user.get_full_name()
            teacher_brand = user.get_associated_teacher_brand()

            # rotate refresh if needed
            if api_settings.ROTATE_REFRESH_TOKENS:
                if api_settings.BLACKLIST_AFTER_ROTATION:
                    try:
                        refresh.blacklist()
                    except AttributeError:
                        pass
                refresh = RefreshToken.for_user(user)
                refresh['username'] = user.username
                refresh['role'] = user.role
                refresh['session_token'] = user.session_token
                refresh['full_name'] = full_name

            access = refresh.access_token
            access['username'] = user.username
            access['role'] = user.role
            access['session_token'] = user.session_token
            access['full_name'] = full_name

            return {
                'access': str(access),
                'refresh': str(refresh),
                'username': user.username,
                'full_name': full_name,
                'role': user.role,
                'session_token': user.session_token,
                'teacher_brand': teacher_brand
            }

        except TokenError as e:
            msg = 'Invalid token'
            if 'wrong type' in str(e).lower():
                msg = 'Wrong token type – use refresh token'
            elif 'expired' in str(e).lower():
                msg = 'Refresh token expired'
            raise serializers.ValidationError(msg)





class AssistantProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        source='user.username',
        required=False,
        allow_blank=False
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=8
    )
    teacher = serializers.PrimaryKeyRelatedField(
        queryset=TeacherProfile.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = AssistantProfile
        fields = [
            'id', 'teacher', 'full_name', 'phone_number', 'gender',
            'user', 'username', 'password'
        ]
        read_only_fields = ['id', 'user']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['teacher'] = {
            'id': instance.teacher.id,
            'full_name': instance.teacher.full_name
        }
        rep['username'] = instance.user.username
        return rep

    def validate_teacher(self, value):
        request = self.context.get('request')
        if request and request.user.role == 'teacher':
            if value != request.user.teacher_profile:
                raise serializers.ValidationError(
                    "You can only assign assistants to yourself"
                )
        return value

    def validate(self, data):
        # Phone number validation
        phone = data.get('phone_number', '')
        if phone and len(phone) != 11:
            raise serializers.ValidationError(
                {'phone_number': 'Phone number must be 11 digits'}
            )

        # Password validation (if provided)
        password = data.get('password')
        if password and len(password) < 8:
            raise serializers.ValidationError(
                {'password': 'Password must be at least 8 characters'}
            )

        return data

    def create(self, validated_data):
        # Extract user-related data from the top level of validated_data
        # The `source='user.username'` on the serializer field nests the username
        # data. We need to extract it from the 'user' dictionary.
        user_data_from_source = validated_data.pop('user', {})
        username = user_data_from_source.get('username')
        password = validated_data.pop('password', None)

        # For creation, both username and password are required.
        if not username or not password:
            raise serializers.ValidationError("Username and password are required to create an assistant.")

        # Prepare data for UserSerializer
        user_data = {
            'username': username,
            'password': password,
            'role': 'assistant'
        }

        # Create User account
        user_serializer = UserSerializer(data=user_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()

        # Create AssistantProfile
        return AssistantProfile.objects.create(user=user, **validated_data)

    def update(self, instance, validated_data):
        # Extract user data and password
        user_data = validated_data.pop('user', {})
        password = validated_data.pop('password', None)

        # Update AssistantProfile fields
        instance = super().update(instance, validated_data)

        # Update associated User account
        user = instance.user
        update_user = False

        # Update username if provided
        if 'username' in user_data:
            new_username = user_data['username']
            if user.username != new_username:
                user.username = new_username
                update_user = True

        # Update password if provided
        if password:
            user.set_password(password)
            update_user = True

        # Save user if any changes were made
        if update_user:
            user.save()

        return instance