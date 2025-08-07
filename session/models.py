#session/models.py

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from accounts.models import TeacherProfile, StudentProfile, Grade, Center

class Session(models.Model):
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name='teaching_sessions'
    )
    grade = models.ForeignKey(
        Grade,
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    center = models.ForeignKey(
        Center,
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    date = models.DateField(default=timezone.now)
    title = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    has_homework = models.BooleanField(
        default=False,
        verbose_name="Has Homework"
    )
    has_test = models.BooleanField(
        default=False,
        verbose_name="Has Test"
    )
    test_max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Test Max Score"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        unique_together = [['teacher', 'grade', 'center', 'date']]

    def __str__(self):
        return f"{self.date} - {self.grade.name} - {self.center.name}"

    def clean(self):
        """Validate teacher-center relationship and grade assignment"""
        # Validate teacher owns the center
        if self.center.teacher != self.teacher:
            raise ValidationError("Center does not belong to this teacher")
        
        # Validate teacher teaches this grade
        if not self.teacher.grades.filter(id=self.grade.id).exists():
            raise ValidationError("Teacher is not assigned to this grade")

class SessionAttendance(models.Model):
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='session_attendance'
    )
    attended = models.BooleanField(default=False)

    class Meta:
        unique_together = [['session', 'student']]
        verbose_name = 'Session Attendance'
        verbose_name_plural = 'Session Attendance Records'

    def clean(self):
        """Validate student belongs to session's grade and teacher's center"""
        # Validate student is in the same grade as session
        if self.student.grade != self.session.grade:
            raise ValidationError("Student doesn't belong to this session's grade")
        
        # Validate student belongs to session's teacher
        if self.student.center.teacher != self.session.teacher:
            raise ValidationError("Student doesn't belong to this teacher's centers")

    def __str__(self):
        status = "Present" if self.attended else "Absent"
        return f"{self.student.full_name} - {self.session.date} - {status}"

class SessionTestScore(models.Model):
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='test_scores'
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='session_scores'
    )
    score = models.DecimalField(max_digits=5, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['session', 'student']]
        verbose_name = 'Session Test Score'
        verbose_name_plural = 'Session Test Scores'

    def clean(self):
        """Validate score and student relationship"""
        # Validate session has a test and a max score
        if not self.session.has_test or self.session.test_max_score is None:
            raise ValidationError("Cannot add score to a session without a test or max score.")

        # Validate score doesn't exceed max
        if self.score > self.session.test_max_score:
            raise ValidationError("Score exceeds the session's maximum value")
        
        # Validate student is in the same grade as session
        if self.student.grade != self.session.grade:
            raise ValidationError("Student doesn't belong to this session's grade")
        
        # Validate student belongs to session's teacher
        if self.student.center.teacher != self.session.teacher:
            raise ValidationError("Student doesn't belong to this teacher's centers")

    def __str__(self):
        return f"{self.student.full_name}: {self.score}/{self.session.test_max_score} ({self.session.date})"

class SessionHomework(models.Model):
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='homework_records'
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='session_homework'
    )
    completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['session', 'student']]
        verbose_name = 'Session Homework'
        verbose_name_plural = 'Session Homework Records'

    def clean(self):
        """Validate student belongs to session's grade and teacher's center"""
        # Validate student is in the same grade as session
        if self.student.grade != self.session.grade:
            raise ValidationError("Student doesn't belong to this session's grade")
        
        # Validate student belongs to session's teacher
        if self.student.center.teacher != self.session.teacher:
            raise ValidationError("Student doesn't belong to this teacher's centers")

    def __str__(self):
        status = "Completed" if self.completed else "Not Completed"
        return f"{self.student.full_name} - {self.session.date} - {status}"