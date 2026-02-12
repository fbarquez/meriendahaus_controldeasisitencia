"""URL configuration for the clock app."""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.clock_view, name='clock'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('api/status/', views.status_api, name='status_api'),
]
