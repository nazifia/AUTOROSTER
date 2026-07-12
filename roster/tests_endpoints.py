# ponytail: single smoke test hitting every URL, upgrade to per-view tests if logic grows
import datetime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (Hospital, Department, Unit, Staff, StaffAvailability,
                     Roster, RosterEntry, PtechStaffEntry)


class EndpointSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('08000000000', 'pw')
        cls.hospital = Hospital.objects.create(name='H1')
        cls.dept = Department.objects.create(hospital=cls.hospital)
        cls.unit = Unit.objects.create(department=cls.dept, unit_name='U1')
        cls.staff = Staff.objects.create(unit=cls.unit, name='JOHN DOE')
        cls.avail = StaffAvailability.objects.create(
            staff=cls.staff, start_date='2026-07-01', end_date='2026-07-05')
        cls.roster = Roster.objects.create(unit=cls.unit, month=7, year=2026)
        cls.entry = RosterEntry.objects.create(roster=cls.roster, date='2026-07-01')
        cls.ptech_roster = Roster.objects.create(
            unit=cls.unit, month=8, year=2026, roster_type='PTECH', shift_config='M_A_N')
        cls.ptech_entry = PtechStaffEntry.objects.create(
            roster=cls.ptech_roster, staff=cls.staff, date='2026-07-01', shift='M')

    def setUp(self):
        self.client.force_login(self.user)

    def assert_get(self, name, args=None, expect=200):
        resp = self.client.get(reverse(name, args=args or []))
        self.assertEqual(resp.status_code, expect, f'{name}: got {resp.status_code}')

    def test_get_pages(self):
        pk_map = {
            'hospital_detail': self.hospital.pk, 'hospital_edit': self.hospital.pk,
            'hospital_delete': self.hospital.pk,
            'department_edit': self.dept.pk, 'department_delete': self.dept.pk,
            'unit_edit': self.unit.pk, 'unit_delete': self.unit.pk,
            'staff_edit': self.staff.pk, 'staff_delete': self.staff.pk,
            'staff_availability': self.staff.pk,
            'roster_detail': self.roster.pk, 'roster_delete': self.roster.pk,
        }
        for name in ['dashboard', 'hospital_list', 'hospital_create',
                     'department_list', 'department_create',
                     'unit_list', 'unit_create',
                     'staff_list', 'staff_create',
                     'roster_list', 'roster_generate',
                     'activity_log', 'manage_activity_log_access']:
            self.assert_get(name)
        for name, pk in pk_map.items():
            self.assert_get(name, [pk])
        self.assert_get('roster_detail', [self.ptech_roster.pk])

    def test_json_apis(self):
        resp = self.client.get(reverse('units_by_department', args=[self.dept.pk]))
        self.assertEqual(resp.status_code, 200)
        resp.json()
        resp = self.client.get(reverse('staff_by_unit', args=[self.unit.pk]))
        self.assertEqual(resp.status_code, 200)
        resp.json()

    def test_roster_export(self):
        for r in (self.roster, self.ptech_roster):
            resp = self.client.get(reverse('roster_export', args=[r.pk]))
            self.assertEqual(resp.status_code, 200)
            self.assertIn('spreadsheetml', resp['Content-Type'])

    def test_entry_update(self):
        resp = self.client.get(reverse('entry_update', args=[self.entry.pk]))
        self.assertEqual(resp.status_code, 405)
        resp = self.client.post(reverse('entry_update', args=[self.entry.pk]),
                                {'slot1': self.staff.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['slot1'], self.staff.display_name)

    def test_ptech_entry_update(self):
        resp = self.client.post(reverse('ptech_entry_update', args=[self.ptech_entry.pk]),
                                {'shift': 'A'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['shift'], 'A')
        resp = self.client.post(reverse('ptech_entry_update', args=[self.ptech_entry.pk]),
                                {'shift': 'ZZ'})
        self.assertEqual(resp.status_code, 400)

    def test_auth_required(self):
        self.client.logout()
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_accounts_pages(self):
        self.client.logout()
        for name in ('login', 'register'):
            self.assert_get(name)
