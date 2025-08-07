from django.contrib import admin
from .models import StudyWeek, StudyMaterial
from django import forms
from django.contrib import messages
from django.utils import timezone
from django.utils.html import format_html
from accounts.models import TeacherProfile, Center
import pytz

class StudyWeekForm(forms.ModelForm):
    class Meta:
        model = StudyWeek
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        teacher = cleaned_data.get('teacher')
        centers = cleaned_data.get('centers')

        # Only validate if we have both teacher and centers
        if teacher and centers:
            for center in centers.all():
                if center.teacher != teacher:
                    self.add_error(
                        'centers',
                        f"Center '{center.name}' does not belong to teacher '{teacher.full_name}'"
                    )
        return cleaned_data

class StudyWeekAdmin(admin.ModelAdmin):
    form = StudyWeekForm
    list_display = ('id','title', 'teacher', 'grade', 'local_date_created')
    list_filter = ('teacher', 'grade', 'date_created')
    search_fields = ('title', 'description')
    filter_horizontal = ('centers',)
    readonly_fields = ('local_date_created',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        # Limit centers to those belonging to the teacher
        if obj and obj.teacher:
            form.base_fields['centers'].queryset = Center.objects.filter(teacher=obj.teacher)
        return form

    def local_date_created(self, obj):
        """Display date_created in Africa/Cairo timezone"""
        if obj.date_created:
            cairo_tz = pytz.timezone('Africa/Cairo')
            local_time = timezone.localtime(obj.date_created, timezone=cairo_tz)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        return None
    local_date_created.short_description = 'Date Created (Local)'
    local_date_created.admin_order_field = 'date_created'

    def save_model(self, request, obj, form, change):
        # First save the StudyWeek instance
        super().save_model(request, obj, form, change)

        # Now handle centers
        centers = form.cleaned_data.get('centers')
        if centers:
            obj.centers.set(centers)

        # Show warning if any centers don't belong to teacher
        for center in obj.centers.all():
            if center.teacher != obj.teacher:
                self.message_user(
                    request,
                    f"Warning: Center '{center.name}' doesn't belong to teacher '{obj.teacher.full_name}'",
                    level=messages.WARNING
                )

    def save_related(self, request, form, formsets, change):
        # This ensures centers are properly saved in the admin
        super().save_related(request, form, formsets, change)
        form.instance.save()

class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'teacher', 'week', 'material_type', 'local_date_created')
    list_filter = ('teacher', 'week', 'material_type', 'date_created')
    search_fields = ('title', 'text_content')
    readonly_fields = ('file_url', 'local_date_created')

    def local_date_created(self, obj):
        """Display date_created in Africa/Cairo timezone"""
        if obj.date_created:
            cairo_tz = pytz.timezone('Africa/Cairo')
            local_time = timezone.localtime(obj.date_created, timezone=cairo_tz)
            return local_time.strftime("%Y-%m-%d %H:%M:%S")
        return None
    local_date_created.short_description = 'Date Created (Local)'
    local_date_created.admin_order_field = 'date_created'

    def file_url(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">{}</a>',
                              obj.file.url,
                              obj.file.name)
        return "No file"
    file_url.short_description = "File URL"

# Register models with custom admin classes
admin.site.register(StudyWeek, StudyWeekAdmin)
admin.site.register(StudyMaterial, StudyMaterialAdmin)