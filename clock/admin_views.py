"""
Custom admin views for dashboard, reports, and utilities.
"""

from datetime import timedelta, date
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum, Count, F, ExpressionWrapper, DurationField, Q
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.contrib.auth.models import User
from django.http import HttpResponse

from .models import TimeEntry, Location


@staff_member_required
def admin_dashboard(request):
    """
    Main dashboard with summary statistics.
    """
    now = timezone.now()
    today = now.date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    # Currently clocked in
    open_entries = TimeEntry.objects.filter(
        check_out__isnull=True
    ).select_related('user', 'location').order_by('-check_in')

    # Today's entries
    today_entries = TimeEntry.objects.filter(
        check_in__date=today
    ).select_related('user', 'location')

    # Alerts: entries open for more than 12 hours
    twelve_hours_ago = now - timedelta(hours=12)
    stale_entries = TimeEntry.objects.filter(
        check_out__isnull=True,
        check_in__lt=twelve_hours_ago
    ).select_related('user', 'location')

    # Alerts: entries without checkout from previous days
    yesterday = today - timedelta(days=1)
    forgotten_entries = TimeEntry.objects.filter(
        check_out__isnull=True,
        check_in__date__lt=today
    ).select_related('user', 'location')

    # Stats for today
    today_stats = {
        'total_entries': today_entries.count(),
        'completed': today_entries.filter(check_out__isnull=False).count(),
        'open': today_entries.filter(check_out__isnull=True).count(),
        'manual': today_entries.filter(is_manual=True).count(),
    }

    # Stats for this week
    week_entries = TimeEntry.objects.filter(check_in__date__gte=start_of_week)
    week_stats = {
        'total_entries': week_entries.count(),
        'unique_employees': week_entries.values('user').distinct().count(),
    }

    # Calculate total hours this week
    week_completed = week_entries.filter(check_out__isnull=False)
    total_minutes = 0
    for entry in week_completed:
        if entry.duration_minutes:
            total_minutes += entry.duration_minutes
    week_stats['total_hours'] = round(total_minutes / 60, 1)

    # Recent manual entries (need attention)
    recent_manual = TimeEntry.objects.filter(
        is_manual=True,
        check_in__date__gte=start_of_week
    ).select_related('user', 'modified_by').order_by('-modified_at')[:5]

    # Overtime entries this week (more than 8 hours)
    overtime_entries = []
    for entry in week_completed:
        if entry.duration_minutes and entry.duration_minutes > 480:
            overtime_entries.append(entry)

    context = {
        'title': 'Dashboard',
        'now': now,
        'today': today,
        'open_entries': open_entries,
        'today_stats': today_stats,
        'week_stats': week_stats,
        'stale_entries': stale_entries,
        'forgotten_entries': forgotten_entries,
        'recent_manual': recent_manual,
        'overtime_entries': overtime_entries[:5],
        'overtime_count': len(overtime_entries),
    }

    return render(request, 'admin/clock/dashboard.html', context)


@staff_member_required
def who_is_here(request):
    """
    View showing who is currently clocked in.
    """
    open_entries = TimeEntry.objects.filter(
        check_out__isnull=True
    ).select_related('user', 'location').order_by('check_in')

    # Calculate how long each person has been here
    now = timezone.now()
    entries_with_duration = []
    for entry in open_entries:
        duration = now - entry.check_in
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)
        entries_with_duration.append({
            'entry': entry,
            'hours': hours,
            'minutes': minutes,
            'is_long': hours >= 8,
            'is_very_long': hours >= 12,
        })

    # Employees not clocked in today
    today = now.date()
    clocked_in_users = TimeEntry.objects.filter(
        check_in__date=today
    ).values_list('user_id', flat=True)

    not_clocked_in = User.objects.filter(
        is_active=True,
        is_staff=False
    ).exclude(id__in=clocked_in_users)

    context = {
        'title': '¿Quién está ahora?',
        'entries': entries_with_duration,
        'total_present': len(entries_with_duration),
        'not_clocked_in': not_clocked_in,
        'now': now,
    }

    return render(request, 'admin/clock/who_is_here.html', context)


@staff_member_required
def hours_summary(request):
    """
    Summary of hours per employee for week/month.
    """
    today = timezone.now().date()

    # Get filter parameters
    period = request.GET.get('period', 'week')

    if period == 'month':
        start_date = today.replace(day=1)
        period_name = today.strftime('%B %Y')
    elif period == 'last_month':
        first_of_month = today.replace(day=1)
        last_month = first_of_month - timedelta(days=1)
        start_date = last_month.replace(day=1)
        end_date = first_of_month - timedelta(days=1)
        period_name = last_month.strftime('%B %Y')
    else:  # week
        start_date = today - timedelta(days=today.weekday())
        period_name = f"Semana del {start_date.strftime('%d/%m')}"

    # Get all active employees
    employees = User.objects.filter(is_active=True).order_by('first_name', 'username')

    # Calculate hours for each employee
    employee_data = []
    for emp in employees:
        if period == 'last_month':
            entries = TimeEntry.objects.filter(
                user=emp,
                check_in__date__gte=start_date,
                check_in__date__lte=end_date,
                check_out__isnull=False
            )
        else:
            entries = TimeEntry.objects.filter(
                user=emp,
                check_in__date__gte=start_date,
                check_out__isnull=False
            )

        total_minutes = sum(e.duration_minutes or 0 for e in entries)
        total_hours = round(total_minutes / 60, 2)

        # Count days worked
        days_worked = entries.values('check_in__date').distinct().count()

        # Count overtime entries
        overtime_count = sum(1 for e in entries if e.duration_minutes and e.duration_minutes > 480)

        # Count manual entries
        manual_count = entries.filter(is_manual=True).count()

        # Open entry?
        open_entry = TimeEntry.objects.filter(user=emp, check_out__isnull=True).first()

        employee_data.append({
            'user': emp,
            'total_hours': total_hours,
            'total_entries': entries.count(),
            'days_worked': days_worked,
            'overtime_count': overtime_count,
            'manual_count': manual_count,
            'avg_hours_per_day': round(total_hours / days_worked, 2) if days_worked > 0 else 0,
            'open_entry': open_entry,
        })

    # Sort by total hours descending
    employee_data.sort(key=lambda x: x['total_hours'], reverse=True)

    # Totals
    totals = {
        'hours': sum(e['total_hours'] for e in employee_data),
        'entries': sum(e['total_entries'] for e in employee_data),
        'overtime': sum(e['overtime_count'] for e in employee_data),
    }

    context = {
        'title': 'Resumen de Horas',
        'period': period,
        'period_name': period_name,
        'employee_data': employee_data,
        'totals': totals,
        'today': today,
    }

    return render(request, 'admin/clock/hours_summary.html', context)


@staff_member_required
def employee_detail(request, user_id):
    """
    Detailed view of a single employee's history.
    """
    from django.shortcuts import get_object_or_404

    employee = get_object_or_404(User, pk=user_id)
    today = timezone.now().date()

    # Get filter
    days = int(request.GET.get('days', 30))
    start_date = today - timedelta(days=days)

    entries = TimeEntry.objects.filter(
        user=employee,
        check_in__date__gte=start_date
    ).order_by('-check_in')

    # Calculate stats
    completed_entries = [e for e in entries if e.check_out]
    total_minutes = sum(e.duration_minutes or 0 for e in completed_entries)

    stats = {
        'total_entries': entries.count(),
        'completed': len(completed_entries),
        'open': entries.filter(check_out__isnull=True).count(),
        'total_hours': round(total_minutes / 60, 2),
        'manual': entries.filter(is_manual=True).count(),
        'overtime': sum(1 for e in completed_entries if e.duration_minutes and e.duration_minutes > 480),
    }

    # Group by date for daily summary
    daily_summary = {}
    for entry in entries:
        date_key = entry.check_in.date()
        if date_key not in daily_summary:
            daily_summary[date_key] = {
                'date': date_key,
                'entries': [],
                'total_minutes': 0,
            }
        daily_summary[date_key]['entries'].append(entry)
        if entry.duration_minutes:
            daily_summary[date_key]['total_minutes'] += entry.duration_minutes

    # Convert to list and sort
    daily_list = sorted(daily_summary.values(), key=lambda x: x['date'], reverse=True)
    for day in daily_list:
        day['total_hours'] = round(day['total_minutes'] / 60, 2)

    context = {
        'title': f'Historial: {employee.get_full_name() or employee.username}',
        'employee': employee,
        'entries': entries,
        'stats': stats,
        'daily_summary': daily_list,
        'days': days,
        'start_date': start_date,
    }

    return render(request, 'admin/clock/employee_detail.html', context)


@staff_member_required
def calendar_view(request):
    """
    Calendar view of entries for a month.
    """
    import calendar

    today = timezone.now().date()

    # Get month/year from params
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    # Build calendar
    cal = calendar.Calendar(firstweekday=0)  # Monday first
    month_days = cal.monthdatescalendar(year, month)

    # Get entries for this month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    entries = TimeEntry.objects.filter(
        check_in__date__gte=first_day,
        check_in__date__lte=last_day
    ).select_related('user', 'location')

    # Group entries by date
    entries_by_date = {}
    for entry in entries:
        date_key = entry.check_in.date()
        if date_key not in entries_by_date:
            entries_by_date[date_key] = []
        entries_by_date[date_key].append(entry)

    # Build weeks with entry data
    weeks = []
    for week in month_days:
        week_data = []
        for day in week:
            day_entries = entries_by_date.get(day, [])
            week_data.append({
                'date': day,
                'is_current_month': day.month == month,
                'is_today': day == today,
                'entries': day_entries,
                'entry_count': len(day_entries),
                'has_open': any(e.is_open for e in day_entries),
                'has_overtime': any(e.duration_minutes and e.duration_minutes > 480 for e in day_entries),
            })
        weeks.append(week_data)

    # Navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    context = {
        'title': 'Calendario',
        'weeks': weeks,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'today': today,
    }

    return render(request, 'admin/clock/calendar.html', context)


@staff_member_required
def generate_qr(request, location_id):
    """
    Generate QR code for a location.
    """
    from django.shortcuts import get_object_or_404
    import qrcode
    import qrcode.image.svg
    from io import BytesIO

    location = get_object_or_404(Location, pk=location_id)

    # Generate QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(location.code)
    qr.make(fit=True)

    # Check format
    fmt = request.GET.get('format', 'png')

    if fmt == 'svg':
        img = qr.make_image(image_factory=qrcode.image.svg.SvgImage)
        buffer = BytesIO()
        img.save(buffer)
        response = HttpResponse(buffer.getvalue(), content_type='image/svg+xml')
        response['Content-Disposition'] = f'inline; filename="qr_{location.code}.svg"'
    else:
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        response = HttpResponse(buffer.getvalue(), content_type='image/png')
        response['Content-Disposition'] = f'inline; filename="qr_{location.code}.png"'

    return response


@staff_member_required
def qr_print_page(request, location_id):
    """
    Printable page with QR code and instructions.
    """
    from django.shortcuts import get_object_or_404

    location = get_object_or_404(Location, pk=location_id)

    context = {
        'location': location,
        'title': f'QR Code - {location.name}',
    }

    return render(request, 'admin/clock/qr_print.html', context)


@staff_member_required
def close_forgotten_entries(request):
    """
    Close all forgotten entries from previous days.
    """
    from django.contrib import messages
    from django.shortcuts import redirect

    if request.method == 'POST':
        today = timezone.now().date()

        forgotten = TimeEntry.objects.filter(
            check_out__isnull=True,
            check_in__date__lt=today
        )

        count = forgotten.count()

        for entry in forgotten:
            # Set checkout to end of that day (23:59)
            end_of_day = timezone.make_aware(
                timezone.datetime.combine(entry.check_in.date(), timezone.datetime.max.time())
            )
            entry.check_out = end_of_day
            entry.check_out_ip = 'AUTO_CLOSED'
            entry.is_manual = True
            entry.notes = (entry.notes or '') + f'\n[Auto-cerrado por admin el {timezone.now().strftime("%d/%m/%Y %H:%M")}]'
            entry.modified_by = request.user
            entry.save()

        messages.success(request, f'Se cerraron {count} fichajes olvidados.')
        return redirect('admin:clock_timeentry_changelist')

    # GET - show confirmation
    today = timezone.now().date()
    forgotten = TimeEntry.objects.filter(
        check_out__isnull=True,
        check_in__date__lt=today
    ).select_related('user', 'location')

    context = {
        'title': 'Cerrar fichajes olvidados',
        'forgotten': forgotten,
        'count': forgotten.count(),
    }

    return render(request, 'admin/clock/close_forgotten.html', context)
