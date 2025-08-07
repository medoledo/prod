from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User , StudentProfile , TeacherProfile , AssistantProfile , Center , Grade , Subject ,Payment

class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Role", {"fields": ("role",)}),
    )
    list_display = ('id',"username", "email", "role", "is_staff", "is_active")

class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('id','full_name', 'phone_number', 'gender', 'subject', 'user')
    search_fields = ('full_name', 'phone_number', 'user__username')
    list_filter = ('subject',)

class AssistantProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'phone_number', 'gender', 'teacher')
    search_fields = ('full_name', 'phone_number', 'teacher__full_name')
    list_filter = ('teacher',)

class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('id','full_name', 'phone_number', 'parent_number', 'teacher', 'grade', 'center')
    search_fields = ('full_name', 'teacher__full_name', 'grade__name', 'center__name')
    list_filter = ('teacher', 'grade', 'center')

class CenterAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'teacher')
    search_fields = ('name', 'teacher__full_name')

class GradeAdmin(admin.ModelAdmin):
    list_display = ('id','name',)
    search_fields = ('name',)

class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id','name',)
    search_fields = ('name',)

admin.site.register(User , UserAdmin)
admin.site.register(TeacherProfile, TeacherProfileAdmin)
admin.site.register(AssistantProfile, AssistantProfileAdmin)
admin.site.register(StudentProfile, StudentProfileAdmin)
admin.site.register(Center, CenterAdmin)
admin.site.register(Grade, GradeAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Payment)



