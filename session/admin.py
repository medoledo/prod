from django.contrib import admin
from .models import Session, SessionAttendance, SessionTestScore, SessionHomework  # Added SessionHomework

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'teacher', 'grade', 'center', 'title', 'has_homework', 'has_test', 'test_max_score')
    list_filter = ('grade', 'center', 'teacher', 'date')
    search_fields = ('title', 'teacher__full_name', 'grade__name', 'center__name')
    date_hierarchy = 'date'
    list_editable = ('has_homework', 'has_test')  # Optional: make editable in list view

@admin.register(SessionAttendance)
class SessionAttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'student', 'attended')
    list_filter = ('attended', 'session__date', 'session__grade')
    search_fields = ('student__full_name', 'session__title')
    raw_id_fields = ('session', 'student')
    list_editable = ('attended',)  # Optional: make editable in list view

@admin.register(SessionTestScore)
class SessionTestScoreAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'student', 'score', 'percentage')
    list_filter = ('session__date', 'session__grade')
    search_fields = ('student__full_name', 'session__title')
    raw_id_fields = ('session', 'student')
    
    def percentage(self, obj):
        if obj.session.test_max_score and obj.session.test_max_score > 0:
            return f"{round((obj.score / obj.session.test_max_score) * 100, 2)}%"
        return "N/A"
    percentage.short_description = 'Score %'

# Added SessionHomeworkAdmin
@admin.register(SessionHomework)
class SessionHomeworkAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'student', 'completed', 'created_at')
    list_filter = ('completed', 'session__date', 'session__grade')
    search_fields = ('student__full_name', 'session__title', 'notes')
    raw_id_fields = ('session', 'student')
    list_editable = ('completed',)  # Optional: make editable in list view
    date_hierarchy = 'created_at'