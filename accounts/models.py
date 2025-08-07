#accounts/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.db import IntegrityError
import random
# Gender Choices
GENDER_CHOICES = (
    ('male', 'Male'),
    ('female', 'Female'),
)

# User model
class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('assistant', 'Assistant'),
        ('student', 'Student'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    session_token = models.CharField(max_length=10, default='0')

    def __str__(self):
        return f"{self.username} ({self.role})"

    def get_full_name(self):
        """
        Returns the full name from the user's associated profile.
        Falls back to the username if no profile or name is found.
        """
        if self.role == 'teacher' and hasattr(self, 'teacher_profile'):
            return self.teacher_profile.full_name
        elif self.role == 'student' and hasattr(self, 'student_profile'):
            return self.student_profile.full_name
        elif self.role == 'assistant' and hasattr(self, 'assistant_profile'):
            return self.assistant_profile.full_name
        return self.username  # Fallback

    def get_associated_teacher_name(self):
        """
        Returns the name of the associated teacher based on user role.
        - For students/assistants, it's their assigned teacher's name.
        - For teachers, it's their own name.
        - For admins, it's None.
        """
        if self.role == 'student' and hasattr(self, 'student_profile'):
            return self.student_profile.teacher.full_name
        elif self.role == 'assistant' and hasattr(self, 'assistant_profile'):
            return self.assistant_profile.teacher.full_name
        elif self.role == 'teacher' and hasattr(self, 'teacher_profile'):
            return self.teacher_profile.full_name
        return None

    def get_associated_teacher_brand(self):
        """
        Returns the brand of the associated teacher based on user role.
        - For students/assistants, it's their assigned teacher's brand.
        - For teachers, it's their own brand.
        - For admins, it's None.
        """
        teacher_profile = None
        if self.role == 'student' and hasattr(self, 'student_profile'):
            teacher_profile = self.student_profile.teacher
        elif self.role == 'assistant' and hasattr(self, 'assistant_profile'):
            teacher_profile = self.assistant_profile.teacher
        elif self.role == 'teacher' and hasattr(self, 'teacher_profile'):
            teacher_profile = self.teacher_profile

        return teacher_profile.brand if teacher_profile else None

# Subject model
class Subject(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

# Grade model
class Grade(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

# Teacher profile
class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=11)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    brand = models.CharField(max_length=100, blank=True, null=True)  # Optional brand field
    grades = models.ManyToManyField('Grade', related_name='teachers')

    def __str__(self):
        return f"Teacher: {self.full_name} (Subject: {self.subject.name if self.subject else 'No subject'})"

# Center model — now scoped to each teacher
class Center(models.Model):
    name = models.CharField(max_length=100)
    teacher = models.ForeignKey('TeacherProfile', on_delete=models.CASCADE, related_name='centers')

    class Meta:
        unique_together = ('name', 'teacher')  # Ensures private center list per teacher

    def __str__(self):
        return f"{self.name} ({self.teacher.full_name})"

# Assistant profile
class AssistantProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='assistant_profile')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='assistants')
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=11)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)

    def __str__(self):
        return f"Assistant: {self.full_name} (Teacher: {self.teacher.full_name})"

# Student profile
class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='students')
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=11)
    parent_number = models.CharField(max_length=11)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT)
    center = models.ForeignKey(Center, on_delete=models.PROTECT)
    is_approved = models.BooleanField(default=False)
    student_id = models.CharField(max_length=6, unique=True, blank=True, editable=False)
    added_by = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Student: {self.full_name} (ID: {self.student_id}, Teacher: {self.teacher.full_name})"

    def generate_unique_student_id(self):
        while True:
            # Generate a random 5-digit number
            new_id = str(random.randint(100000, 999999))
            # Check if ID already exists
            if not StudentProfile.objects.filter(student_id=new_id).exists():
                return new_id

    def save(self, *args, **kwargs):
        if not self.student_id:
            self.student_id = self.generate_unique_student_id()
        try:
            super().save(*args, **kwargs)
        except IntegrityError:
            # Handle the rare case where another student got the same ID between check and save
            self.student_id = self.generate_unique_student_id()
            super().save(*args, **kwargs)

# Payment model for teacher payment history
class Payment(models.Model):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.teacher.full_name} paid {self.amount} on {self.date}"
