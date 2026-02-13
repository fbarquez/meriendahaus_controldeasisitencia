"""
Custom admin views for dashboard and reports.
"""

from datetime import timedelta
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib import messages

from .models import TimeEntry


@staff_member_required
def admin_dashboard(request):
    """
    Main dashboard with summary statistics.
    """
    now = timezone.now()
    today = now.date()
    start_of_week = today - timedelta(days=today.weekday())

    # Currently clocked in
    open_entries = TimeEntry.objects.filter(
        check_out__isnull=True
    ).select_related('user', 'location').order_by('-check_in')

    # Today's entries
    today_entries = TimeEntry.objects.filter(check_in__date=today)

    # Forgotten entries (no checkout from previous days)
    forgotten_entries = TimeEntry.objects.filter(
        check_out__isnull=True,
        check_in__date__lt=today
    ).select_related('user')

    # Stats for today
    today_stats = {
        'total': today_entries.count(),
        'completed': today_entries.filter(check_out__isnull=False).count(),
        'open': today_entries.filter(check_out__isnull=True).count(),
    }

    # Stats for this week
    week_entries = TimeEntry.objects.filter(
        check_in__date__gte=start_of_week,
        check_out__isnull=False
    )
    total_minutes = sum(e.duration_minutes or 0 for e in week_entries)
    week_stats = {
        'total_entries': week_entries.count(),
        'total_hours': round(total_minutes / 60, 1),
    }

    context = {
        'title': 'Dashboard',
        'now': now,
        'open_entries': open_entries,
        'today_stats': today_stats,
        'week_stats': week_stats,
        'forgotten_entries': forgotten_entries,
    }

    return render(request, 'admin/clock/dashboard.html', context)


@staff_member_required
def hours_summary(request):
    """
    Summary of hours per employee for week/month.
    """
    today = timezone.now().date()
    period = request.GET.get('period', 'week')

    if period == 'month':
        start_date = today.replace(day=1)
        period_name = today.strftime('%B %Y')
    else:
        start_date = today - timedelta(days=today.weekday())
        period_name = f"Week of {start_date.strftime('%d/%m')}"

    employees = User.objects.filter(is_active=True).order_by('first_name', 'username')

    employee_data = []
    for emp in employees:
        entries = TimeEntry.objects.filter(
            user=emp,
            check_in__date__gte=start_date,
            check_out__isnull=False
        )

        total_minutes = sum(e.duration_minutes or 0 for e in entries)
        total_hours = round(total_minutes / 60, 2)
        days_worked = entries.values('check_in__date').distinct().count()

        employee_data.append({
            'user': emp,
            'total_hours': total_hours,
            'total_entries': entries.count(),
            'days_worked': days_worked,
        })

    employee_data.sort(key=lambda x: x['total_hours'], reverse=True)

    totals = {
        'hours': sum(e['total_hours'] for e in employee_data),
        'entries': sum(e['total_entries'] for e in employee_data),
    }

    context = {
        'title': 'Hours Summary',
        'period': period,
        'period_name': period_name,
        'employee_data': employee_data,
        'totals': totals,
    }

    return render(request, 'admin/clock/hours_summary.html', context)


@staff_member_required
def close_forgotten_entries(request):
    """
    Close all forgotten entries from previous days.
    """
    today = timezone.now().date()

    if request.method == 'POST':
        forgotten = TimeEntry.objects.filter(
            check_out__isnull=True,
            check_in__date__lt=today
        )

        count = forgotten.count()

        for entry in forgotten:
            end_of_day = timezone.make_aware(
                timezone.datetime.combine(entry.check_in.date(), timezone.datetime.max.time())
            )
            entry.check_out = end_of_day
            entry.check_out_ip = 'AUTO_CLOSED'
            entry.is_manual = True
            entry.notes = (entry.notes or '') + f'\n[Closed by admin {timezone.now().strftime("%d/%m/%Y %H:%M")}]'
            entry.modified_by = request.user
            entry.save()

        messages.success(request, f'{count} forgotten entries closed.')
        return redirect('admin:clock_timeentry_changelist')

    forgotten = TimeEntry.objects.filter(
        check_out__isnull=True,
        check_in__date__lt=today
    ).select_related('user')

    context = {
        'title': 'Close Forgotten Entries',
        'forgotten': forgotten,
        'count': forgotten.count(),
    }

    return render(request, 'admin/clock/close_forgotten.html', context)
