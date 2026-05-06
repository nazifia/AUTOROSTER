from django.db import models
from django.core.exceptions import ValidationError
import calendar


class Hospital(models.Model):
    name = models.CharField(max_length=200, unique=True)
    address = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Department(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='departments', db_index=True)
    department_name = models.CharField(max_length=200, default='PHARMACY DEPARTMENT')

    def __str__(self):
        return f"{self.hospital.name} / {self.department_name}"

    class Meta:
        ordering = ['hospital__name', 'department_name']


class Unit(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='units', db_index=True)
    unit_name = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.department.department_name} — {self.unit_name}"

    class Meta:
        ordering = ['department__department_name', 'unit_name']


class Staff(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='staff', db_index=True)
    title = models.CharField(max_length=50, default='PHARM.')
    name = models.CharField(max_length=200, help_text='Full name e.g. IBRAHIM ABUKUR')
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f"{self.title} {self.name}".upper()

    @property
    def display_name(self):
        return f"{self.title} {self.name}".upper()

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Staff'
        indexes = [
            models.Index(fields=['unit', 'is_active']),
        ]


class StaffAvailability(models.Model):
    """Date range during which a staff member is unavailable."""
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='availability_records', db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    reason = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.staff} unavailable {self.start_date} → {self.end_date}"

    class Meta:
        ordering = ['start_date']
        verbose_name_plural = 'Staff Availability Records'
        indexes = [
            models.Index(fields=['staff_id', 'start_date', 'end_date']),
        ]


MONTH_CHOICES = [(i, calendar.month_name[i]) for i in range(1, 13)]

ROSTER_TYPE_CHOICES = [
    ('CALL', 'Call Duty Roster'),
    ('PTECH', 'PTech Shift Roster'),
]

PTECH_SHIFT_CHOICES = [
    ('M', 'Morning'),
    ('A', 'Afternoon'),
    ('O', 'Off'),
    ('CM', 'Combined Morning'),
    ('L', 'Leave'),
]

# Kept for migration history; no longer used in generation logic.
PTECH_SHIFT_CONFIG_CHOICES = [
    ('MA_N', 'Morning, Afternoon, Night'),
    ('MAN_N', 'Morning-Afternoon, Night'),
    ('MA_NN', 'Morning, Afternoon-Night'),
    ('MAN_NN', 'Morning-Afternoon-Night'),
]

SHIFT_CONFIG_DETAILS = {
    'MA_N': {'num_slots': 3, 'slot1': 'MORNING', 'slot2': 'AFTERNOON', 'slot3': 'NIGHT'},
    'MAN_N': {'num_slots': 2, 'slot1': 'MORNING-AFTERNOON', 'slot2': 'NIGHT', 'slot3': None},
    'MA_NN': {'num_slots': 2, 'slot1': 'MORNING', 'slot2': 'AFTERNOON-NIGHT', 'slot3': None},
    'MAN_NN': {'num_slots': 1, 'slot1': 'MORNING-AFTERNOON-NIGHT', 'slot2': None, 'slot3': None},
}


class Roster(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='rosters', db_index=True)
    roster_title = models.CharField(max_length=200, default="PHARMACISTS' CALL DUTY ROSTER")
    month = models.IntegerField(choices=MONTH_CHOICES, db_index=True)
    year = models.IntegerField(db_index=True)
    roster_type = models.CharField(max_length=10, choices=ROSTER_TYPE_CHOICES, default='CALL', db_index=True)
    shift_config = models.CharField(max_length=10, choices=PTECH_SHIFT_CONFIG_CHOICES, blank=True, null=True, help_text='Required for PTech rosters')
    num_slots = models.IntegerField(default=3, choices=[(1, '1 Slot'), (2, '2 Slots'), (3, '3 Slots')])
    slot1_label = models.CharField(max_length=100, default='FIRST ON CALL')
    slot2_label = models.CharField(max_length=100, default='SECOND ON CALL')
    slot3_label = models.CharField(max_length=100, default='THIRD ON CALL')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.roster_title} — {self.get_month_display()} {self.year}"

    @property
    def month_year_display(self):
        return f"{calendar.month_name[self.month].upper()}, {self.year}."

    def clean(self):
        super().clean()
        if self.roster_type != 'PTECH':
            self.shift_config = None

    class Meta:
        ordering = ['-year', '-month']
        unique_together = ['unit', 'month', 'year']
        indexes = [
            models.Index(fields=['unit', 'month', 'year']),
        ]


class RosterEntry(models.Model):
    roster = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name='entries', db_index=True)
    date = models.DateField(db_index=True)
    slot1 = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='slot1_entries', db_index=True)
    slot2 = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='slot2_entries', db_index=True)
    slot3 = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='slot3_entries', db_index=True)

    @property
    def day_abbr(self):
        return self.date.strftime('%a').upper()

    @property
    def date_display(self):
        return f"{self.date.month}/{self.date.day}/{self.date.year}"

    def __str__(self):
        return f"{self.date} — {self.roster}"

    class Meta:
        ordering = ['date']
        unique_together = ['roster', 'date']
        indexes = [
            models.Index(fields=['roster', 'date']),
        ]


class PtechStaffEntry(models.Model):
    """Per-staff per-day shift assignment for PTech rosters."""
    roster = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name='ptech_entries', db_index=True)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='ptech_entries', db_index=True)
    date = models.DateField(db_index=True)
    shift = models.CharField(max_length=2, choices=PTECH_SHIFT_CHOICES)

    def __str__(self):
        return f"{self.date} {self.staff} — {self.shift}"

    class Meta:
        ordering = ['date', 'staff__name']
        unique_together = ['roster', 'staff', 'date']
        indexes = [
            models.Index(fields=['roster', 'date']),
            models.Index(fields=['roster', 'staff']),
        ]
