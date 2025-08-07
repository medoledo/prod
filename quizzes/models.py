#quizzes/models.py

from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.core.validators import FileExtensionValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from accounts.models import TeacherProfile, StudentProfile, Center, Grade

class Quiz(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='quizzes')
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name='quizzes')
    centers = models.ManyToManyField(Center, through='QuizCenter')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.title
    
    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
        ]

class QuizCenter(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    center = models.ForeignKey(Center, on_delete=models.CASCADE)
    open_date = models.DateTimeField()
    close_date = models.DateTimeField()

    class Meta:
        unique_together = ('quiz', 'center')
        verbose_name = 'Quiz Center Access'
        verbose_name_plural = 'Quiz Center Access'
        indexes = [
            models.Index(fields=['open_date']),
            models.Index(fields=['close_date']),
        ]

class QuizSettings(models.Model):
    quiz = models.OneToOneField(Quiz, on_delete=models.CASCADE, related_name='settings')
    timer_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Duration in minutes (0 = no time limit)",
        validators=[MaxValueValidator(1440, message="Timer cannot exceed one day (1440 minutes).")]
    )
    
    # Updated visibility choices without manual option
    SCORE_VISIBILITY_CHOICES = [
        ('immediate', 'Immediately after submission'),
        ('after_close', 'After quiz is closed'),
        ('manual', 'Manually by teacher/assistant'),
    ]
    score_visibility = models.CharField(
        max_length=20,
        choices=SCORE_VISIBILITY_CHOICES,
        default='after_close'
    )
    
    ANSWERS_VISIBILITY_CHOICES = [
        ('immediate', 'Immediately after submission'),
        ('after_close', 'After quiz is closed'),
        ('manual', 'Manually by teacher/assistant'),
    ]
    answers_visibility = models.CharField(
        max_length=20,
        choices=ANSWERS_VISIBILITY_CHOICES,
        default='after_close'
    )

    QUESTION_ORDER_CHOICES = [
        ('created', 'As created by teacher'),
        ('random', 'Randomly for each student'),
    ]
    question_order = models.CharField(
        max_length=10,
        choices=QUESTION_ORDER_CHOICES,
        default='created',
        help_text="The order in which questions are presented to the student."
    )

class Question(models.Model):
    SINGLE = 'single'
    MULTIPLE = 'multiple'
    SELECTION_TYPES = [
        (SINGLE, 'Single Correct Answer'),
        (MULTIPLE, 'Multiple Correct Answers'),
    ]
    
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    selection_type = models.CharField(
        max_length=10,
        choices=SELECTION_TYPES,
        default=SINGLE
    )
    
    # Removed short answer option
    QUESTION_TYPE_CHOICES = [
        ('mcq', 'Multiple Choice'),
    ]
    question_type = models.CharField(
        max_length=10, 
        choices=QUESTION_TYPE_CHOICES,
        default='mcq'
    )
    
    text = models.TextField(
        blank=True,
        help_text="The question content. Can be blank if an image is provided."
    )
    points = models.PositiveIntegerField(
        default=1,
        help_text="Points awarded for correct answer"
    )
    image = models.ImageField(
        upload_to='question_images/',
        null=True,
        blank=True,
        help_text="Optional image for the question. Allowed formats: jpg, jpeg, png.",
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )
    order = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="The order of the question in the quiz, set by the teacher."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
        ]
        ordering = ['order', 'created_at']
    
    def clean(self):
        """
        Validate that:
        1. The question has either text or an image.
        2. At least one choice is correct (for existing questions with choices).
        """
        # 1. A question must have either text or an image, or both.
        if not self.text and not self.image:
            raise ValidationError("A question must have either text or an image.")
        # 2. Check for correct choice on existing objects
        # This part is more relevant for admin usage, as the API serializer handles this.
        if self.pk and self.choices.exists():
            if not self.choices.filter(is_correct=True).exists():
                raise ValidationError("An existing question with choices must have at least one correct choice.")
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.text} ({self.get_selection_type_display()})"

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices', help_text="The question this choice belongs to.")
    text = models.CharField(max_length=255, blank=True, help_text="The choice text. Can be blank if an image is provided.")
    is_correct = models.BooleanField(
        default=False,
        help_text="Is this the correct answer?"
    )
    image = models.ImageField(
        upload_to='choice_images/',
        null=True,
        blank=True,
        help_text="Optional image for the choice. Allowed formats: jpg, jpeg, png.",
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )

    def clean(self):
        if not self.text and not self.image:
            raise ValidationError("A choice must have either text or an image.")

    def __str__(self):
        return f"{self.text} {'✓' if self.is_correct else ''}"

class QuizSubmission(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(default=0)
    is_submitted = models.BooleanField(default=False)

    is_score_released = models.BooleanField(default=False, help_text="Manually released by teacher")
    are_answers_released = models.BooleanField(default=False, help_text="Manually released by teacher")

    class Meta:
        indexes = [
            models.Index(fields=['start_time']),
            models.Index(fields=['student', 'quiz']),
        ]
        unique_together = ('quiz', 'student')  # Ensure one submission per student

    @property
    def is_timed_out(self):
        """
        Checks if the submission has exceeded its time limit, regardless of
        whether it has been formally submitted. This state is permanent.
        """
        # A submission that was explicitly submitted by the user cannot be timed out.
        if self.is_submitted:
            return False

        # If an end_time is set, it means the submission was finalized (likely by timeout).
        # This state is permanent.
        if self.end_time:
            return True

        # If we reach here, the submission is still in progress.
        # Perform a live check to see if it should be timed out now.

        # If it hasn't started or has no time limit, it can't time out.
        if not self.start_time or self.quiz.settings.timer_minutes == 0:
            return False
        
        # Live check against the deadline.
        try:
            # Calculate the deadline with a 60-second grace period.
            deadline = self.start_time + timedelta(minutes=self.quiz.settings.timer_minutes, seconds=60)
        except OverflowError:
            return False
        return timezone.now() > deadline

    def time_taken(self):
        """
        Returns time taken as a formatted string.
        - Under 60s: "X seconds"
        - 60s or more: "Y minutes"
        """
        if self.end_time and self.start_time:
            seconds = (self.end_time - self.start_time).total_seconds()
            if seconds < 60:
                return f"{int(seconds)} seconds"
            else:
                minutes = seconds / 60.0
                # Format to one decimal place if not a whole number
                return f"{int(minutes)} minutes" if minutes % 1 == 0 else f"{minutes:.1f} minutes"
        return "0 seconds"
    
    def calculate_score(self):
        total_score = 0
        answers_to_update = []
        
        for answer in self.answers.all():
            # Only handle MCQs (no more short answers)
            correct_choices = answer.question.choices.filter(is_correct=True)
            total_correct_choices = correct_choices.count()
            
            selected_correct = answer.selected_choices.filter(is_correct=True).count()
            selected_total = answer.selected_choices.count()
            
            if total_correct_choices > 0:
                # Calculate partial score
                partial_score = (selected_correct / total_correct_choices) * answer.question.points
                
                # Penalty for incorrect selections
                incorrectly_selected = selected_total - selected_correct
                if incorrectly_selected > 0:
                    penalty = (incorrectly_selected / total_correct_choices) * answer.question.points
                    partial_score = max(0, partial_score - penalty)

                answer.points_earned = partial_score
                answer.is_correct = (selected_correct == total_correct_choices and 
                                     selected_total == total_correct_choices)
                total_score += answer.points_earned
                answers_to_update.append(answer)
        
        if answers_to_update:
            Answer.objects.bulk_update(answers_to_update, ['points_earned', 'is_correct'])
            
        # Return the calculated score; let the caller handle saving.
        return total_score
    
    def __str__(self):
        return f"{self.student.user.email} - {self.quiz.title} ({self.score})"

class Answer(models.Model):
    submission = models.ForeignKey(QuizSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    
    # Removed text field (only MCQs supported)
    selected_choices = models.ManyToManyField(
        Choice, 
        related_name='answers',
        blank=True,  # Allows admin flexibility; API serializer enforces requirement
        help_text="Selected choices for the question"
    )
    is_correct = models.BooleanField(default=False)
    points_earned = models.FloatField(default=0)
    order = models.PositiveIntegerField(
        default=0,
        help_text="The order in which this question appeared for the student."
    )
    
    class Meta:
        unique_together = ('submission', 'question')  # One answer per question per submission
        ordering = ['order']
    
    def __str__(self):
        return f"{self.question.text[:50]}... (Score: {self.points_earned}/{self.question.points})"