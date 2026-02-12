"""
URL patterns for custom admin views.
"""

from django.urls import path
from . import admin_views

urlpatterns = [
    path('dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('who-is-here/', admin_views.who_is_here, name='admin_who_is_here'),
    path('hours-summary/', admin_views.hours_summary, name='admin_hours_summary'),
    path('employee/<int:user_id>/', admin_views.employee_detail, name='admin_employee_detail'),
    path('calendar/', admin_views.calendar_view, name='admin_calendar'),
    path('location/<int:location_id>/qr/', admin_views.generate_qr, name='admin_generate_qr'),
    path('location/<int:location_id>/qr-print/', admin_views.qr_print_page, name='admin_qr_print'),
    path('close-forgotten/', admin_views.close_forgotten_entries, name='admin_close_forgotten'),
]
