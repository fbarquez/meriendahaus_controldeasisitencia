"""
Views for the time tracking system.
Simple template-based views with session authentication.
"""

import logging
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.db import transaction

from .models import Location, TimeEntry, FailedClockAttempt
from .ip_utils import get_client_ip, validate_location_access

logger = logging.getLogger(__name__)


def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('clock')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            messages.error(request, 'Enter username and PIN')
            return render(request, 'clock/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                logger.info(f"User {username} logged in from {get_client_ip(request)}")
                return redirect('clock')
            else:
                messages.error(request, 'Your account is disabled')
        else:
            logger.warning(f"Failed login attempt for {username} from {get_client_ip(request)}")
            messages.error(request, 'Invalid username or PIN')

    return render(request, 'clock/login.html')


def logout_view(request):
    """Handle user logout."""
    if request.user.is_authenticated:
        logger.info(f"User {request.user.username} logged out")
        logout(request)
    return redirect('login')


@login_required
def clock_view(request):
    """
    Main view for employees to clock in/out.
    Shows current status and handles clock actions.
    Simple one-button interface with automatic IP validation.
    """
    user = request.user
    open_entry = TimeEntry.get_open_entry(user)
    error = None
    success = None

    # Get the active location (single location setup)
    location = Location.objects.filter(is_active=True).first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if not location:
            error = "No location configured. Contact administrator."
        else:
            # Validate IP
            is_allowed, client_ip, ip_error = validate_location_access(request, location)

            if not is_allowed:
                error = "You must be at the workplace to clock in/out"

                # Record the failed attempt
                FailedClockAttempt.objects.create(
                    user=user,
                    location=location,
                    action=action,
                    ip_address=client_ip
                )

                logger.warning(
                    f"IP validation failed for {user.username}: "
                    f"IP={client_ip}, Location={location.code} - Attempt recorded"
                )
            else:
                # Process action
                if action == 'in':
                    success, error = do_check_in(user, location, client_ip)
                elif action == 'out':
                    success, error = do_check_out(user, location, client_ip)
                else:
                    error = "Invalid action"

                # Refresh open_entry after action
                open_entry = TimeEntry.get_open_entry(user)

    context = {
        'open_entry': open_entry,
        'error': error,
        'success': success,
        'server_time': timezone.now(),
        'location': location,
    }
    return render(request, 'clock/clock.html', context)


@transaction.atomic
def do_check_in(user, location, client_ip):
    """
    Perform check-in for a user.

    Returns:
        Tuple of (success_message: str or None, error_message: str or None)
    """
    # Check if already checked in
    if TimeEntry.has_open_entry(user):
        open_entry = TimeEntry.get_open_entry(user)
        time_str = open_entry.check_in.strftime('%H:%M')
        return None, f"You already clocked in at {time_str}"

    # Create new entry
    now = timezone.now()
    entry = TimeEntry.objects.create(
        user=user,
        location=location,
        check_in=now,
        check_in_ip=client_ip,
        is_manual=False
    )

    logger.info(f"Check-in: {user.username} at {location.code} from IP {client_ip}")
    return f"Clocked in at {now.strftime('%H:%M')}", None


@transaction.atomic
def do_check_out(user, location, client_ip):
    """
    Perform check-out for a user.

    Returns:
        Tuple of (success_message: str or None, error_message: str or None)
    """
    open_entry = TimeEntry.get_open_entry(user)

    if not open_entry:
        return None, "You haven't clocked in yet"

    # Update entry with check-out
    now = timezone.now()
    open_entry.check_out = now
    open_entry.check_out_ip = client_ip
    open_entry.save()

    duration = open_entry.duration_display
    logger.info(
        f"Check-out: {user.username} at {location.code} from IP {client_ip} "
        f"(duration: {duration})"
    )
    return f"Clocked out at {now.strftime('%H:%M')} (Duration: {duration})", None


@login_required
def status_api(request):
    """
    Simple JSON endpoint to get current status.
    Useful for PWA to check status without full page reload.
    """
    from django.http import JsonResponse

    user = request.user
    open_entry = TimeEntry.get_open_entry(user)

    data = {
        'has_open_entry': open_entry is not None,
        'server_time': timezone.now().isoformat(),
    }

    if open_entry:
        data['open_entry'] = {
            'check_in': open_entry.check_in.isoformat(),
            'location': open_entry.location.name,
        }

    return JsonResponse(data)
