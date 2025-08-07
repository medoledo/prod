#studymaterials/serializers.py


import pytz
from rest_framework import serializers
from .models import StudyWeek, StudyMaterial
from accounts.models import Grade, Center

class StudyWeekSerializer(serializers.ModelSerializer):
    grade = serializers.PrimaryKeyRelatedField(
        queryset=Grade.objects.all(),
        required=True,
        help_text="Grade ID this week is assigned to"
    )
    centers = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Center.objects.all(),
        required=True,
        help_text="List of center IDs that can access this week"
    )

    class Meta:
        model = StudyWeek
        fields = ['id', 'teacher', 'title', 'description', 'grade', 'centers', 'date_created']
        read_only_fields = ['teacher', 'date_created']
        extra_kwargs = {
            'title': {'required': True, 'allow_blank': False},
            'description': {'required': False, 'allow_blank': True}
        }

    def get_teacher(self):
        """Helper to get teacher profile from request context"""
        request = self.context.get('request')
        if request and request.user:
            if request.user.role == 'teacher':
                return request.user.teacher_profile
            elif request.user.role == 'assistant':
                return request.user.assistant_profile.teacher
        return None

    def validate(self, attrs):
        """Validate grade and center assignments"""
        teacher = self.get_teacher()
        if not teacher:
            raise serializers.ValidationError(
                {"role": "Only teachers/assistants can create weeks"},
                code='invalid_role'
            )

        # Validate grade assignment
        grade = attrs.get('grade')
        if grade and not teacher.grades.filter(id=grade.id).exists():
            raise serializers.ValidationError(
                {"grade": f"Teacher is not assigned to grade {grade.name}"},
                code='invalid_grade_assignment'
            )

        # Validate center assignments
        centers = attrs.get('centers', [])
        for center in centers:
            if center.teacher != teacher:
                raise serializers.ValidationError(
                    {"centers": f"Center '{center.name}' does not belong to your teacher profile"},
                    code='invalid_center_assignment'
                )

        return attrs

    def create(self, validated_data):
        """Handle week creation with teacher assignment"""
        centers = validated_data.pop('centers', [])
        teacher = self.get_teacher()
        if not teacher:
            raise serializers.ValidationError(
                {"role": "Only teachers/assistants can create weeks"},
                code='invalid_role'
            )

        validated_data['teacher'] = teacher
        instance = super().create(validated_data)

        # Add centers after saving the instance
        instance.centers.set(centers)
        return instance

    def update(self, instance, validated_data):
        """Handle week updates with validation"""
        centers = validated_data.pop('centers', None)

        # Update other fields
        instance = super().update(instance, validated_data)

        # Update centers if provided
        if centers is not None:
            # Validate centers
            teacher = instance.teacher
            for center in centers:
                if center.teacher != teacher:
                    raise serializers.ValidationError(
                        {"centers": f"Center '{center.name}' does not belong to your teacher profile"},
                        code='invalid_center_update'
                    )
            instance.centers.set(centers)

        return instance

    def to_representation(self, instance):
        """Enhanced representation with detailed grade and center info"""
        representation = super().to_representation(instance)
        request = self.context.get('request')

        # Convert UTC to Africa/Cairo timezone
        cairo_tz = pytz.timezone('Africa/Cairo')
        if instance.date_created:
            # Ensure datetime is timezone-aware
            if instance.date_created.tzinfo is None:
                utc_time = pytz.utc.localize(instance.date_created)
            else:
                utc_time = instance.date_created

            # Convert to Cairo time
            cairo_time = utc_time.astimezone(cairo_tz)
            representation['date_created'] = cairo_time.strftime("%Y-%m-%d %H:%M:%S")

        # Replace grade ID with detailed grade object
        representation['grade'] = {
            'id': instance.grade.id,
            'name': instance.grade.name
        }

        # Conditionally include centers based on user role for data privacy.
        # Students should not see all centers where a week is available.
        if request and request.user.role in ['teacher', 'assistant', 'admin']:
            representation['centers'] = [
                {
                    'id': center.id,
                    'name': center.name,
                    'teacher_id': center.teacher.id,
                    'teacher_name': center.teacher.full_name
                }
                for center in instance.centers.all()
            ]
        elif 'centers' in representation:
            del representation['centers']

        return representation

class StudyMaterialSerializer(serializers.ModelSerializer):
    week = serializers.PrimaryKeyRelatedField(
        queryset=StudyWeek.objects.all(),
        required=True,
        help_text="Week ID this material belongs to"
    )

    # New field for file URL (read-only)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = StudyMaterial
        fields = [
            'id', 'teacher', 'week', 'title', 'material_type',
            'file', 'file_url', 'text_content', 'external_url', 'date_created'
        ]
        read_only_fields = ['teacher', 'date_created', 'file_url']
        extra_kwargs = {
            'title': {'required': True, 'allow_blank': False},
            'material_type': {'required': True},
            'file': {
                'required': False,
                'allow_null': True,
                'write_only': True  # Hide in responses
            },
            'text_content': {'required': False, 'allow_blank': True},
            'external_url': {'required': False, 'allow_blank': True},
        }

    def get_teacher(self):
        """Helper to get teacher profile from request context"""
        request = self.context.get('request')
        if request and request.user:
            if request.user.role == 'teacher':
                return request.user.teacher_profile
            elif request.user.role == 'assistant':
                return request.user.assistant_profile.teacher
        return None

    def get_file_url(self, obj):
        """Generate absolute URL for file if it exists"""
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

    def validate(self, attrs):
        """Validate material content and permissions"""
        material_type = attrs.get('material_type')
        week = attrs.get('week')

        # Get teacher based on user role
        teacher = self.get_teacher()
        if not teacher:
            raise serializers.ValidationError(
                {"role": "Invalid content creator role"},
                code='invalid_role'
            )

        # Validate week ownership
        if week and week.teacher != teacher:
            raise serializers.ValidationError(
                {"week": "You don't have permission for this study week"},
                code='invalid_week_ownership'
            )

        # Validate grade assignment through week
        if week and not teacher.grades.filter(id=week.grade.id).exists():
            raise serializers.ValidationError(
                {"week": f"Teacher is not assigned to grade {week.grade.name}"},
                code='invalid_week_grade'
            )

        # Material type validation with constants
        errors = {}
        if material_type == StudyMaterial.MATERIAL_TYPE_PDF:
            if not attrs.get('file'):
                errors['file'] = "PDF materials must have a file uploaded"

        elif material_type == StudyMaterial.MATERIAL_TYPE_VIDEO:
            if not attrs.get('file') and not attrs.get('external_url'):
                errors['general'] = "Video materials require either a file or external URL"

        elif material_type == StudyMaterial.MATERIAL_TYPE_IMAGE:
            if not attrs.get('file'):
                errors['file'] = "Image materials must have a file uploaded"

        elif material_type == StudyMaterial.MATERIAL_TYPE_TEXT:
            if not attrs.get('text_content'):
                errors['text_content'] = "Text materials must have text content"

        elif material_type == StudyMaterial.MATERIAL_TYPE_LINK:
            if not attrs.get('external_url'):
                errors['external_url'] = "Link materials must have an external URL"

        if errors:
            raise serializers.ValidationError(errors, code='invalid_material_content')

        return attrs

    def create(self, validated_data):
        """Handle material creation with teacher assignment"""
        teacher = self.get_teacher()
        if not teacher:
            raise serializers.ValidationError(
                {"role": "Invalid content creator role"},
                code='invalid_role'
            )

        validated_data['teacher'] = teacher

        # Remove file field if it's empty to prevent null issues
        if 'file' in validated_data and validated_data['file'] is None:
            del validated_data['file']

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Handle material updates with file management"""
        # Handle file deletion if new file is provided
        if 'file' in validated_data:
            # Delete old file if it exists and is being replaced
            if instance.file and validated_data['file'] != instance.file:
                instance.file.delete(save=False)
            # Remove file field if it's empty
            if validated_data['file'] is None:
                validated_data['file'] = instance.file
        else:
            # Keep existing file if not provided
            validated_data['file'] = instance.file

        # Handle other fields
        for field in ['text_content', 'external_url']:
            if field not in validated_data:
                validated_data[field] = getattr(instance, field)

        return super().update(instance, validated_data)

    def to_representation(self, instance):
        """Enhanced representation with additional details"""
        representation = super().to_representation(instance)

        # Add material type display name
        representation['material_type_display'] = instance.get_material_type_display()

        # Convert UTC to Africa/Cairo timezone
        cairo_tz = pytz.timezone('Africa/Cairo')
        if instance.date_created:
            # Ensure datetime is timezone-aware
            if instance.date_created.tzinfo is None:
                utc_time = pytz.utc.localize(instance.date_created)
            else:
                utc_time = instance.date_created

            # Convert to Cairo time
            cairo_time = utc_time.astimezone(cairo_tz)
            representation['date_created'] = cairo_time.strftime("%Y-%m-%d %H:%M:%S")

        # Add teacher details
        representation['teacher_details'] = {
            'id': instance.teacher.id,
            'full_name': instance.teacher.full_name
        }

        # Add week details
        representation['week_details'] = {
            'id': instance.week.id,
            'title': instance.week.title,
            'grade': {
                'id': instance.week.grade.id,
                'name': instance.week.grade.name
            }
        }

        return representation