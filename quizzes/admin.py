# quizzes/admin.py

from django.contrib import admin
from django.db.models import Count, Q, F
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from datetime import timedelta
from .models import Quiz, QuizCenter, QuizSettings, Question, Choice, QuizSubmission, Answer

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    fields = ('text', 'image', 'image_preview', 'is_correct')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" height="40" />', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Image'
    ordering = ('id',)

class QuizCenterInline(admin.TabularInline):
    model = QuizCenter
    extra = 0
    fields = ('center', 'open_date', 'close_date')
    ordering = ('open_date',)
    autocomplete_fields = ['center']

class QuizSettingsInline(admin.StackedInline):
    model = QuizSettings
    # extra = 0 # extra is not needed with min_num
    min_num = 1
    max_num = 1
    fields = ('timer_minutes', 'score_visibility', 'answers_visibility', 'question_order')
    can_delete = False

class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    fields = ('text', 'selection_type', 'points', 'image', 'image_display')
    show_change_link = True
    # NOTE: Inlines cannot be nested. The ChoiceInline is managed on the QuestionAdmin page.

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ('question', 'selected_choices', 'is_correct', 'points_earned')
    readonly_fields = ('is_correct', 'points_earned')
    autocomplete_fields = ['question', 'selected_choices']

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'teacher_link', 'grade', 'view_questions_link', 'submission_count', 'created_at')
    list_filter = ('grade', 'teacher__user__email', 'created_at')
    search_fields = ('title', 'description', 'teacher__user__email')
    fields = ('id', 'title', 'description', 'teacher', 'grade')
    readonly_fields = ('id',)
    inlines = [QuizSettingsInline, QuizCenterInline] # Removed QuestionInline for better UX
    autocomplete_fields = ['teacher', 'grade']
    actions = ['release_all_scores', 'release_all_answers']
    list_per_page = 20

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('teacher__user', 'grade').annotate(
            _question_count=Count('questions', distinct=True),
            _submission_count=Count('submissions', distinct=True)
        )

    def teacher_link(self, obj):
        if obj.teacher and obj.teacher.user:
            url = reverse('admin:accounts_teacherprofile_change', args=[obj.teacher.id])
            return format_html('<a href="{}">{}</a>', url, obj.teacher.user.email)
        return "N/A"
    teacher_link.short_description = "Teacher"
    teacher_link.admin_order_field = 'teacher__user__email'

    def view_questions_link(self, obj):
        count = obj._question_count
        url = reverse('admin:quizzes_question_changelist') + f'?quiz__id__exact={obj.id}'
        return format_html('<a href="{}">{} Questions</a>', url, count)
    view_questions_link.short_description = "Questions"
    view_questions_link.admin_order_field = '_question_count'

    def submission_count(self, obj):
        return obj._submission_count
    submission_count.short_description = "Submissions"
    submission_count.admin_order_field = '_submission_count'  # Corrected typo

    def release_all_scores(self, request, queryset):
        """Admin action to release scores for all submissions of the selected quizzes."""
        updated_count = 0
        for quiz in queryset.select_related('settings'):
            if quiz.settings.score_visibility == 'manual':
                # Bulk update all submissions for this quiz
                count = QuizSubmission.objects.filter(quiz=quiz, is_submitted=True).update(is_score_released=True)
                updated_count += count
        self.message_user(request, f"Successfully released scores for {updated_count} total submissions across the selected quizzes.")
    release_all_scores.short_description = "Release scores for ALL submissions (Manual only)"

    def release_all_answers(self, request, queryset):
        """Admin action to release answers for all submissions of the selected quizzes."""
        updated_count = 0
        for quiz in queryset.select_related('settings'):
            if quiz.settings.answers_visibility == 'manual':
                # Bulk update all submissions for this quiz
                count = QuizSubmission.objects.filter(quiz=quiz, is_submitted=True).update(are_answers_released=True)
                updated_count += count
        self.message_user(request, f"Successfully released answers for {updated_count} total submissions across the selected quizzes.")
    release_all_answers.short_description = "Release answers for ALL submissions (Manual only)"  # Corrected typo

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'truncated_text', 'quiz_link', 'selection_type', 'points', 'choice_count', 'image_preview')
    list_filter = ('quiz', 'selection_type')
    search_fields = ('text', 'quiz__title')
    fields = ('id', 'quiz', 'selection_type', 'text', 'points', 'image', 'image_display')
    readonly_fields = ('id', 'image_display',)
    inlines = [ChoiceInline]
    autocomplete_fields = ['quiz']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('quiz').annotate(_choice_count=Count('choices'))

    def truncated_text(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    truncated_text.short_description = 'Text'
    
    def quiz_link(self, obj):
        if obj.quiz:
            url = reverse('admin:quizzes_quiz_change', args=[obj.quiz.id])
            return format_html('<a href="{}">{}</a>', url, obj.quiz.title)
        return "N/A"
    quiz_link.short_description = "Quiz"
    quiz_link.admin_order_field = 'quiz__title'

    def choice_count(self, obj):
        return obj._choice_count
    choice_count.short_description = "Choices"
    
    def image_display(self, obj):
        if obj.image:
            return format_html('<img src="{}" height="150" />', obj.image.url)
        return "No Image"
    image_display.short_description = 'Image Preview'

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" height="40" />', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Image'

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" height="40" />', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Image'

@admin.register(QuizSubmission)
class QuizSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'quiz', 'student_link', 'score', 'is_submitted', 'submission_status',
        'effective_score_status', 'effective_answers_status'
    )
    list_filter = ('quiz', 'is_submitted', 'start_time', 'is_score_released', 'are_answers_released')
    search_fields = ('student__full_name', 'student__user__email', 'quiz__title')
    list_per_page = 20
    autocomplete_fields = ['quiz', 'student']
    inlines = [AnswerInline]
    actions = ['recalculate_scores', 'release_scores', 'release_answers']

    def get_queryset(self, request):
        """Optimize queryset for new display methods."""
        return super().get_queryset(request).select_related(
            'quiz__settings',
            'student__user',
            'student__center'
        ).prefetch_related('quiz__quizcenter_set')

    def _get_effective_status(self, obj, visibility_type):
        """Helper to compute the effective status for score or answers."""
        settings = obj.quiz.settings
        visibility_setting = getattr(settings, f'{visibility_type}_visibility')

        if visibility_type == 'score':
            is_manually_released = obj.is_score_released
        else:  # Assumes 'answers'
            is_manually_released = obj.are_answers_released
        if visibility_setting == 'immediate':
            return format_html('<span style="color: green;">Released</span> (Immediate)')
        
        if visibility_setting == 'manual':
            status_text = "Released" if is_manually_released else "Not Released"
            color = "green" if is_manually_released else "orange"
            return format_html(f'<span style="color: {color};">{status_text}</span> (Manual)')

        if visibility_setting == 'after_close':
            # Find the specific close date for the student's center
            quiz_center = next((qc for qc in obj.quiz.quizcenter_set.all() if qc.center_id == obj.student.center_id), None)
            if not quiz_center:
                return format_html('<span style="color: red;">Error: Center not found</span>')

            effective_release_time = quiz_center.close_date
            if settings.timer_minutes > 0:
                try:
                    effective_release_time += timedelta(minutes=settings.timer_minutes)
                except OverflowError:
                    # If timer is too large, it's not closed yet.
                    return format_html('<span style="color: orange;">Pending</span> (Invalid Timer)')

            if timezone.now() > effective_release_time:
                return format_html('<span style="color: green;">Released</span> (After Close)')
            else:
                local_release_time = timezone.localtime(effective_release_time)
                return format_html('<span style="color: orange;">Pending</span> (until {})', local_release_time.strftime('%b %d, %-I:%M %p'))

        return "Unknown"

    def effective_score_status(self, obj):
        return self._get_effective_status(obj, 'score')
    effective_score_status.short_description = "Score Status"

    def effective_answers_status(self, obj):
        return self._get_effective_status(obj, 'answers')
    effective_answers_status.short_description = "Answers Status"

    def get_readonly_fields(self, request, obj=None):
        # On creation, only the calculated score is read-only.
        if obj is None:
            return ('score',)
        # On update, quiz and student cannot be changed.
        return ('id', 'quiz', 'student')

    def student_link(self, obj):
        if obj.student and obj.student.user:
            url = reverse('admin:accounts_studentprofile_change', args=[obj.student.id])
            return format_html('<a href="{}">{}</a>', url, obj.student.user.email)
        return "N/A"
    student_link.short_description = "Student"

    def recalculate_scores(self, request, queryset):
        """Admin action to manually trigger score calculation."""
        updated_count = 0
        for submission in queryset:
            if submission.is_submitted:
                submission.score = submission.calculate_score()
                submission.save(update_fields=['score'])
                updated_count += 1
        self.message_user(request, f"Successfully recalculated scores for {updated_count} submissions.")
    recalculate_scores.short_description = "Recalculate scores for selected submissions"

    def release_scores(self, request, queryset):
        """Admin action to manually release scores."""
        # Only release for submissions where the quiz setting is 'manual'
        queryset_to_update = queryset.filter(quiz__settings__score_visibility='manual')
        updated_count = queryset_to_update.update(is_score_released=True)
        self.message_user(request, f"Successfully released scores for {updated_count} submissions.")
    release_scores.short_description = "Release scores for selected submissions (Manual only)"

    def release_answers(self, request, queryset):
        """Admin action to manually release answers."""
        # Only release for submissions where the quiz setting is 'manual'
        queryset_to_update = queryset.filter(quiz__settings__answers_visibility='manual')
        updated_count = queryset_to_update.update(are_answers_released=True)
        self.message_user(request, f"Successfully released answers for {updated_count} submissions.")
    release_answers.short_description = "Release answers for selected submissions (Manual only)"

    def submission_status(self, obj):
        """Determines if the submission was on time or late."""
        if not obj.is_submitted:
            return "In Progress"
        if not obj.start_time or not obj.end_time:
            return 'Pending'
        
        timer_minutes = obj.quiz.settings.timer_minutes
        if timer_minutes == 0:
            return format_html('<span style="color: green;">On Time</span>')
            
        time_taken_seconds = (obj.end_time - obj.start_time).total_seconds()
        allowed_seconds = (timer_minutes * 60) + 60 # 60s grace period
        
        return format_html('<span style="color: green;">On Time</span>') if time_taken_seconds <= allowed_seconds else format_html('<span style="color: red;">Late</span>')
    submission_status.short_description = "Status"


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('id', 'question', 'submission', 'points_earned', 'is_correct', 'answer_preview')
    list_filter = ('is_correct', 'question__quiz')
    search_fields = ('question__text', 'submission__student__full_name')
    readonly_fields = ('id', 'submission', 'question', 'selected_choices', 'is_correct', 'points_earned')

    def answer_preview(self, obj):
        selected = ", ".join([str(c) for c in obj.selected_choices.all()])
        return f"Selected: {selected}" if selected else "No choice selected"
    answer_preview.short_description = "Response"

@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'truncated_text', 'question', 'is_correct', 'answer_count')
    list_filter = ('is_correct', 'question__quiz')
    search_fields = ('text', 'question__text')
    autocomplete_fields = ['question']
    readonly_fields = ('id',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(answer_count=Count('answers'))

    def truncated_text(self, obj):
        return obj.text[:30] + '...' if len(obj.text) > 30 else obj.text
    truncated_text.short_description = 'Text'

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" height="40" />', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Image'

    def answer_count(self, obj):
        return obj.answer_count
    answer_count.short_description = "Times Selected"
    answer_count.admin_order_field = 'answer_count'

# Register remaining models with basic configuration
@admin.register(QuizCenter)
class QuizCenterAdmin(admin.ModelAdmin):
    list_display = ('id', 'quiz', 'center', 'open_date', 'close_date', 'status')
    list_filter = ('center', 'quiz__grade')
    search_fields = ('quiz__title', 'center__name')
    autocomplete_fields = ['quiz', 'center']
    readonly_fields = ('id',)

    def status(self, obj):
        now = timezone.now()
        if now < obj.open_date:
            return "Upcoming"
        if now > obj.close_date:
            return "Closed"
        return "Open"
    status.short_description = "Status"  # Corrected typo

@admin.register(QuizSettings)
class QuizSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'quiz', 'timer_minutes', 'score_visibility', 'answers_visibility')
    search_fields = ('quiz__title',)
    autocomplete_fields = ['quiz']
    readonly_fields = ('id',)