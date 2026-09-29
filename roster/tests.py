from django.test import TestCase

from .models import Department, Hospital, Roster, Staff, Unit
from .utils import generate_roster_entries


class Slot1WeeklyRotationTests(TestCase):
    def test_seven_staff_never_repeat_last_weeks_weekday(self):
        unit = Unit.objects.create(
            department=Department.objects.create(hospital=Hospital.objects.create(name='H')),
            unit_name='U')
        staff = [Staff.objects.create(unit=unit, name=f'S{i}') for i in range(7)]
        roster = Roster.objects.create(unit=unit, month=7, year=2026, num_slots=1)

        generate_roster_entries(roster, staff, [], [])

        by_date = {e.date: e.slot1_id for e in roster.entries.all()}
        for d, sid in by_date.items():
            prev = by_date.get(d.fromordinal(d.toordinal() - 7))
            if prev:
                self.assertNotEqual(sid, prev, d)
        self.assertTrue(all(by_date.values()))
