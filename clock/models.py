"""
Models for the time tracking system.
Simplified version with django-simple-history for audit trail.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from simple_history.models import HistoricalRecords


class Location(models.Model):
    """
    Represents a physical location (local) where employees can clock in/out.
    For this simple version, we expect only one location (LOCAL_01).
    """
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Unique code for QR (e.g., LOCAL_01)"
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., Meriendahaus Principal)"
    )
    allowed_ips = models.JSONField(
        default=list,
        help_text="List of allowed public IPs or CIDRs, e.g., [\"85.123.45.67\", \"192.168.1.0/24\"]"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Track all changes
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Location"
        verbose_name_plural = "Locations"

    def __str__(self):
        return f"{self.code} - {self.name}"


class TimeEntry(models.Model):
    """
    Represents a single clock-in/clock-out pair for an employee.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='time_entries',
        verbose_name="Employee"
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='time_entries',
        verbose_name="Location"
    )
    check_in = models.DateTimeField(verbose_name="Clock In")
    check_out = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Clock Out"
    )

    # Technical info
    check_in_ip = models.GenericIPAddressField(verbose_name="Clock In IP")
    check_out_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="Clock Out IP"
    )

    # Manual entry tracking
    is_manual = models.BooleanField(
        default=False,
        verbose_name="Manual Entry",
        help_text="True if created/modified by admin"
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Notes",
        help_text="Required when is_manual=True (reason for manual entry)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='modified_entries',
        verbose_name="Modified By"
    )

    # Track all changes automatically
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Time Entry"
        verbose_name_plural = "Time Entries"
        ordering = ['-check_in']
        indexes = [
            models.Index(fields=['user', 'check_in']),
            models.Index(fields=['user', '-check_in']),
        ]

    def __str__(self):
        date_str = self.check_in.strftime('%Y-%m-%d %H:%M')
        return f"{self.user.get_full_name() or self.user.username} - {date_str}"

    @property
    def is_open(self):
        """Returns True if this entry has no check_out."""
        return self.check_out is None

    @property
    def duration_minutes(self):
        """Returns duration in minutes, or None if still open."""
        if self.check_out:
            delta = self.check_out - self.check_in
            return int(delta.total_seconds() / 60)
        return None

    @property
    def duration_display(self):
        """Returns formatted duration string."""
        minutes = self.duration_minutes
        if minutes is None:
            return "In progress"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins:02d}m"

    @classmethod
    def get_open_entry(cls, user):
        """Get the open entry for a user, if any."""
        return cls.objects.filter(user=user, check_out__isnull=True).first()

    @classmethod
    def has_open_entry(cls, user):
        """Check if user has an open entry."""
        return cls.objects.filter(user=user, check_out__isnull=True).exists()


class FailedClockAttempt(models.Model):
    """
    Records when an employee tries to clock in/out from outside the allowed network.
    Used for audit and monitoring purposes.
    """
    ACTION_CHOICES = [
        ('in', 'Clock In'),
        ('out', 'Clock Out'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='failed_attempts',
        verbose_name="Employee"
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        related_name='failed_attempts',
        verbose_name="Location"
    )
    action = models.CharField(
        max_length=3,
        choices=ACTION_CHOICES,
        verbose_name="Action attempted"
    )
    ip_address = models.GenericIPAddressField(verbose_name="IP Address")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Timestamp")

    class Meta:
        verbose_name = "Failed Clock Attempt"
        verbose_name_plural = "Failed Clock Attempts"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
