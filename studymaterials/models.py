#studymaterials/models.py

import os
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import TeacherProfile, Grade, Center
from django.db.models.signals import pre_delete
from django.dispatch import receiver
import uuid

def study_material_upload_path(instance, filename):
    """
    Generate a unique, secure, and anonymous file path:
    study_materials/<uuid[0:2]>/<uuid[2:4]>/<uuid>.<ext>
    This prevents filename collisions and hides all identifiable information.
    """
    ext = os.path.splitext(filename)[1].lower()  # Get the file extension, ensure lowercase
    new_uuid = uuid.uuid4()
    new_filename = f"{new_uuid}{ext}"
    return os.path.join(
        'study_materials',
        str(new_uuid)[:2],
        str(new_uuid)[2:4],
        new_filename
    )

class StudyWeek(models.Model):
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name='study_weeks'
    )
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        help_text="Grade this study week is assigned to"
    )
    centers = models.ManyToManyField(
        Center,
        related_name='study_weeks',
        help_text="Centers that can access this study week"
    )
    date_created = models.DateTimeField(
        auto_now_add=True,
        help_text="Date when the study week was created"
    )

    class Meta:
        ordering = ['-date_created', 'title']
        # Removed unique constraint to allow duplicate titles

    def __str__(self):
        return f"{self.title} ({self.teacher.full_name})"

class StudyMaterial(models.Model):
    MATERIAL_TYPE_PDF = 'pdf'
    MATERIAL_TYPE_VIDEO = 'video'
    MATERIAL_TYPE_IMAGE = 'image'
    MATERIAL_TYPE_TEXT = 'text'
    MATERIAL_TYPE_LINK = 'link'

    MATERIAL_TYPE_CHOICES = (
        (MATERIAL_TYPE_PDF, 'PDF'),
        (MATERIAL_TYPE_VIDEO, 'Video'),
        (MATERIAL_TYPE_IMAGE, 'Image'),
        (MATERIAL_TYPE_TEXT, 'Text'),
        (MATERIAL_TYPE_LINK, 'External Link'),
    )

    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name='materials'
    )
    week = models.ForeignKey(
        StudyWeek,
        on_delete=models.CASCADE,
        related_name='materials'
    )
    title = models.CharField(max_length=100)
    material_type = models.CharField(
        max_length=10,
        choices=MATERIAL_TYPE_CHOICES
    )
    file = models.FileField(
        upload_to=study_material_upload_path,
        blank=True,
        null=True,
        help_text="Upload file for PDF, Video, or Image types"
    )
    text_content = models.TextField(
        blank=True,
        help_text="Text content for Text type materials"
    )
    external_url = models.URLField(
        blank=True,
        help_text="External URL for Video or Link type materials"
    )
    date_created = models.DateTimeField(
        auto_now_add=True,
        help_text="Date when the study material was created"
    )

    class Meta:
        ordering = ['-date_created', 'title']

    def __str__(self):
        return f"{self.title} ({self.get_material_type_display()}) - {self.teacher.full_name}"

    def clean(self):
        """
        Validate material content based on type.
        This is called during model validation (admin forms, etc.)
        API serializers perform additional validation.
        """
        # Validate content existence based on material type
        if self.material_type == self.MATERIAL_TYPE_PDF:
            if not self.file:
                raise ValidationError("PDF materials must have a file uploaded")

        elif self.material_type == self.MATERIAL_TYPE_VIDEO:
            if not (self.file or self.external_url):
                raise ValidationError("Video materials require either a file or external URL")

        elif self.material_type == self.MATERIAL_TYPE_IMAGE:
            if not self.file:
                raise ValidationError("Image materials must have a file uploaded")

        elif self.material_type == self.MATERIAL_TYPE_TEXT:
            if not self.text_content:
                raise ValidationError("Text materials must have text content")

        elif self.material_type == self.MATERIAL_TYPE_LINK:
            if not self.external_url:
                raise ValidationError("Link materials must have an external URL")

        # Validate teacher-week relationship
        if self.week.teacher != self.teacher:
            raise ValidationError(
                "Study week does not belong to this teacher"
            )

        # Validate teacher-grade relationship
        if not self.teacher.grades.filter(id=self.week.grade.id).exists():
            raise ValidationError(
                f"Teacher is not assigned to grade {self.week.grade.name}"
            )

    def get_file_url(self, request=None):
        """
        Get absolute URL for the file if it exists
        :param request: HttpRequest object to build absolute URL
        :return: Absolute URL or relative path if no request provided
        """
        if self.file:
            if request:
                return request.build_absolute_uri(self.file.url)
            return self.file.url
        return None

    def get_absolute_url(self):
        """For admin compatibility"""
        if self.file:
            return self.file.url
        if self.external_url:
            return self.external_url
        return '#'

@receiver(pre_delete, sender=StudyMaterial)
def delete_studymaterial_file(sender, instance, **kwargs):
    """
    Deletes file from filesystem when corresponding `StudyMaterial` object is deleted.
    """
    if instance.file:
        instance.file.delete(save=False)