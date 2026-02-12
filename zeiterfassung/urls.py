"""URL configuration for Zeiterfassung project."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/clock/', include('clock.admin_urls')),  # Custom admin views
    path('admin/', admin.site.urls),
    path('', include('clock.urls')),
]
