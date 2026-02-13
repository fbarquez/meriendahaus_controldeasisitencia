"""
Django Admin configuration for the time tracking system.
Simplified version for small teams.
"""

import csv
from datetime import timedelta
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html
from django import forms

from simple_history.admin import SimpleHistoryAdmin

from .models import Location, TimeEntry, FailedClockAttempt


# -----------------------------------------------------------------------------
# Custom Admin Site
# -----------------------------------------------------------------------------

class TimeClockAdminSite(admin.AdminSite):
    site_header = 'Meriendahaus - Time Clock'
    site_title = 'Time Clock'
    index_title = 'Administration'


admin.site = TimeClockAdminSite(name='admin')


# -----------------------------------------------------------------------------
# Location Admin (simplified)
# -----------------------------------------------------------------------------

@admin.register(Location, site=admin.site)
class LocationAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'is_active', 'get_ips_display')
    list_filter = ('is_active',)

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'is_active')
        }),
        ('IP Configuration', {
            'fields': ('allowed_ips',),
            'description': 'Allowed IPs/CIDRs for clocking. Format: ["192.168.1.0/24", "2003:da::/32"]'
        }),
    )

    def get_ips_display(self, obj):
        ips = obj.allowed_ips or []
        if not ips:
            return format_html('<span style="color: #e53e3e;">Not configured</span>')
        return format_html('<code>{}</code>', ', '.join(str(ip) for ip in ips[:2]))
    get_ips_display.short_description = 'Allowed IPs'


# -----------------------------------------------------------------------------
# TimeEntry Admin (simplified)
# -----------------------------------------------------------------------------

class TimeEntryForm(forms.ModelForm):
    """Custom form that requires notes for manual entries."""

    class Meta:
        model = TimeEntry
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        notes = cleaned_data.get('notes', '').strip()

        if self.instance.pk or cleaned_data.get('is_manual', False):
            if len(notes) < 10:
                raise forms.ValidationError(
                    'Notes required for manual entries (min 10 characters)'
                )
        return cleaned_data


class PeriodFilter(admin.SimpleListFilter):
    title = 'Period'
    parameter_name = 'period'

    def lookups(self, request, model_admin):
        return [
            ('today', 'Today'),
            ('week', 'This week'),
            ('month', 'This month'),
        ]

    def queryset(self, request, queryset):
        today = timezone.now().date()

        if self.value() == 'today':
            return queryset.filter(check_in__date=today)
        elif self.value() == 'week':
            start = today - timedelta(days=today.weekday())
            return queryset.filter(check_in__date__gte=start)
        elif self.value() == 'month':
            return queryset.filter(
                check_in__year=today.year,
                check_in__month=today.month
            )
        return queryset


@admin.register(TimeEntry, site=admin.site)
class TimeEntryAdmin(SimpleHistoryAdmin):
    form = TimeEntryForm
    list_display = (
        'get_employee',
        'get_date',
        'get_check_in_time',
        'get_check_out_time',
        'get_duration',
        'get_status'
    )
    list_filter = (PeriodFilter, 'user', 'is_manual')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    date_hierarchy = 'check_in'
    raw_id_fields = ('user',)
    readonly_fields = ('check_in_ip', 'check_out_ip', 'created_at', 'modified_at', 'modified_by')
    list_per_page = 50
    actions = ['export_csv', 'close_entries']

    fieldsets = (
        ('Entry', {
            'fields': ('user', 'location', 'check_in', 'check_out')
        }),
        ('Manual Entry', {
            'fields': ('is_manual', 'notes'),
            'description': 'Mark as manual and explain the reason when correcting entries.'
        }),
        ('Technical', {
            'fields': ('check_in_ip', 'check_out_ip', 'created_at', 'modified_at', 'modified_by'),
            'classes': ('collapse',)
        }),
    )

    def get_employee(self, obj):
        return obj.user.get_full_name() or obj.user.username
    get_employee.short_description = 'Employee'
    get_employee.admin_order_field = 'user__first_name'

    def get_date(self, obj):
        return obj.check_in.strftime('%d/%m/%Y')
    get_date.short_description = 'Date'
    get_date.admin_order_field = 'check_in'

    def get_check_in_time(self, obj):
        return obj.check_in.strftime('%H:%M')
    get_check_in_time.short_description = 'In'

    def get_check_out_time(self, obj):
        if obj.check_out:
            return obj.check_out.strftime('%H:%M')
        return '—'
    get_check_out_time.short_description = 'Out'

    def get_duration(self, obj):
        return obj.duration_display
    get_duration.short_description = 'Duration'

    def get_status(self, obj):
        if obj.is_open:
            return format_html('<span style="color: #3182ce;">Open</span>')
        if obj.is_manual:
            return format_html('<span style="color: #d69e2e;">Manual</span>')
        return format_html('<span style="color: #38a169;">OK</span>')
    get_status.short_description = 'Status'

    def save_model(self, request, obj, form, change):
        if change:
            obj.modified_by = request.user
            obj.is_manual = True
        else:
            obj.is_manual = True
            obj.check_in_ip = 'ADMIN'
            if obj.check_out:
                obj.check_out_ip = 'ADMIN'
        super().save_model(request, obj, form, change)

    @admin.action(description='Export to CSV')
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="time_entries_{timezone.now().strftime("%Y%m%d")}.csv"'
        response.write('\ufeff')

        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Employee', 'Date', 'In', 'Out', 'Duration', 'Manual', 'Notes'])

        for entry in queryset.select_related('user', 'location'):
            writer.writerow([
                entry.user.get_full_name() or entry.user.username,
                entry.check_in.strftime('%d/%m/%Y'),
                entry.check_in.strftime('%H:%M'),
                entry.check_out.strftime('%H:%M') if entry.check_out else '',
                entry.duration_display,
                'Yes' if entry.is_manual else 'No',
                entry.notes or ''
            ])
        return response

    @admin.action(description='Close open entries')
    def close_entries(self, request, queryset):
        count = 0
        for entry in queryset.filter(check_out__isnull=True):
            entry.check_out = timezone.now()
            entry.check_out_ip = 'ADMIN'
            entry.is_manual = True
            entry.notes = (entry.notes or '') + f'\n[Closed by admin]'
            entry.modified_by = request.user
            entry.save()
            count += 1
        self.message_user(request, f'{count} entries closed.')


# -----------------------------------------------------------------------------
# User Admin (simplified)
# -----------------------------------------------------------------------------

class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'get_name', 'is_active', 'get_status')
    list_filter = ('is_active',)

    def get_name(self, obj):
        return obj.get_full_name() or '—'
    get_name.short_description = 'Name'

    def get_status(self, obj):
        if TimeEntry.objects.filter(user=obj, check_out__isnull=True).exists():
            return format_html('<span style="color: #38a169; font-weight: 600;">PRESENT</span>')
        return '—'
    get_status.short_description = 'Status'


admin.site.register(User, CustomUserAdmin)


# -----------------------------------------------------------------------------
# Failed Clock Attempts Admin
# -----------------------------------------------------------------------------

@admin.register(FailedClockAttempt, site=admin.site)
class FailedClockAttemptAdmin(admin.ModelAdmin):
    list_display = ('get_employee', 'action', 'ip_address', 'timestamp')
    list_filter = ('action', 'timestamp')
    date_hierarchy = 'timestamp'
    readonly_fields = ('user', 'location', 'action', 'ip_address', 'timestamp')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_employee(self, obj):
        return obj.user.get_full_name() or obj.user.username
    get_employee.short_description = 'Employee'
