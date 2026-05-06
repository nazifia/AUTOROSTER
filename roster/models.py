from django.db import models
import calendar


class Hospital(models.Model):
    name = models.CharField(max_length=200, unique=True)
    address = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Department(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='departments')
    department_name = models.CharField(max_length=200, default='PHARMACY DEPARTMENT')

    def __str__(self):
        return f"{self.hospital.name} / {self.department_name}"

    class Meta:
        ordering = ['hospital__name', 'department_name']


class Unit(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='units')
    unit_name = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.department.department_name} — {self.unit_name}"

    class Meta:
        ordering = ['department__department_name', 'unit_name']


class Staff(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='staff')
    title = models.CharField(max_length=50, default='PHARM.')
    name = models.CharField(max_length=200, help_text='Full name e.g. IBRAHIM ABUKUR')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} {self.name}".upper()

    @property
    def display_name(self):
        return f"{self.title} {self.name}".upper()

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Staff'


class StaffAvailability(models.Model):
    """Date range during which a staff member is unavailable."""
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='availability_records')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.staff} unavailable {self.start_date} → {self.end_date}"

    class Meta:
        ordering = ['start_date']
        verbose_name_plural = 'Staff Availability Records'


MONTH_CHOICES = [(i, calendar.month_name[i]) for i in range(1, 13)]


class Roster(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='rosters')
    roster_title = models.CharField(max_length=200, default="PHARMACISTS' CALL DUTY ROSTER")
    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField()
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

    class Meta:
        ordering = ['-year', '-month']
        unique_together = ['unit', 'month', 'year']


class RosterEntry(models.Model):
    roster = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name='entries')
    date = models.DateField()
    slot1 = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='slot1_entries')
    slot2 = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='slot2_entries')
    slot3 = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name='slot3_entries')

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
