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
        verbose_name = "Local"
        verbose_name_plural = "Locales"

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
        verbose_name="Empleado"
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='time_entries',
        verbose_name="Local"
    )
    check_in = models.DateTimeField(verbose_name="Entrada")
    check_out = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Salida"
    )

    # Technical info
    check_in_ip = models.GenericIPAddressField(verbose_name="IP entrada")
    check_out_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP salida"
    )

    # Manual entry tracking
    is_manual = models.BooleanField(
        default=False,
        verbose_name="Entrada manual",
        help_text="True if created/modified by admin"
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Notas",
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
        verbose_name="Modificado por"
    )

    # Track all changes automatically
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Fichaje"
        verbose_name_plural = "Fichajes"
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
            return "En curso"
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
