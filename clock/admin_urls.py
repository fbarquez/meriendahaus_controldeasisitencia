"""
URL patterns for custom admin views.
"""

from django.urls import path
from . import admin_views

urlpatterns = [
    path('dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('hours-summary/', admin_views.hours_summary, name='admin_hours_summary'),
    path('close-forgotten/', admin_views.close_forgotten_entries, name='admin_close_forgotten'),
]
