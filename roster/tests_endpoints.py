# ponytail: one smoke suite over the JSON API, upgrade to per-view tests if logic grows
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (ActivityLog, Hospital, Department, Unit, Staff, StaffAvailability,
                     Roster, RosterEntry, PtechStaffEntry)


class ApiSmokeTests(TestCase):
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
            roster=cls.ptech_roster, staff=cls.staff, date='2026-08-01', shift='M')

    def setUp(self):
        self.client.force_login(self.user)

    def get_json(self, name, args=None, expect=200):
        resp = self.client.get(reverse(name, args=args or []))
        self.assertEqual(resp.status_code, expect, f'{name}: got {resp.status_code}')
        return resp.json()

    def test_spa_shell(self):
        self.client.logout()
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('csrftoken', resp.cookies)
        self.assertEqual(self.client.get('/app.js').status_code, 200)

    def test_get_endpoints(self):
        for name in ['lookups', 'dashboard', 'hospital_list', 'department_list', 'unit_list',
                     'staff_list', 'roster_list', 'roster_generate', 'activity_log',
                     'manage_activity_log_access']:
            self.get_json(name)
        for name, pk in [('hospital_detail', self.hospital.pk), ('department_detail', self.dept.pk),
                         ('unit_detail', self.unit.pk), ('staff_detail', self.staff.pk),
                         ('staff_availability', self.staff.pk)]:
            self.get_json(name, [pk])

    def test_roster_detail(self):
        call = self.get_json('roster_detail', [self.roster.pk])
        self.assertFalse(call['is_ptech'])
        self.assertEqual(call['entries'][0]['id'], self.entry.pk)
        ptech = self.get_json('roster_detail', [self.ptech_roster.pk])
        self.assertTrue(ptech['is_ptech'])
        self.assertEqual(len(ptech['dates']), 31)
        self.assertEqual(ptech['rows'][0]['cells'][0], {'id': self.ptech_entry.pk, 'shift': 'M'})

    def test_crud_and_logging(self):
        resp = self.client.post(reverse('hospital_list'), {'name': 'H2'})
        self.assertEqual(resp.status_code, 201)
        pk = resp.json()['id']
        resp = self.client.post(reverse('hospital_list'), {'name': 'h2'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('name', resp.json()['errors'])
        resp = self.client.post(reverse('hospital_detail', args=[pk]), {'name': 'H3'})
        self.assertEqual(resp.json()['name'], 'H3')
        self.assertEqual(self.client.delete(reverse('hospital_detail', args=[pk])).status_code, 200)
        self.assertFalse(Hospital.objects.filter(pk=pk).exists())
        self.assertEqual(list(ActivityLog.objects.values_list('action', flat=True).order_by('timestamp')),
                         ['created', 'updated', 'deleted'])

    def test_admin_only_writes(self):
        plain = get_user_model().objects.create_user('08011111111', 'pw')
        self.client.force_login(plain)
        self.assertEqual(self.client.post(reverse('hospital_list'), {'name': 'X'}).status_code, 403)
        self.assertEqual(self.client.delete(reverse('unit_detail', args=[self.unit.pk])).status_code, 403)
        self.get_json('activity_log', expect=403)
        # Staff are editable by any signed-in user.
        resp = self.client.post(reverse('staff_list'), {'unit': self.unit.pk, 'staff_type': 'PHARM',
                                                        'title': 'PHARM.', 'name': 'JANE'})
        self.assertEqual(resp.status_code, 201)

    def test_generate_call_roster(self):
        resp = self.client.post(reverse('roster_generate'), {
            'unit': self.unit.pk, 'roster_title': 'T', 'roster_type': 'CALL', 'month': 9, 'year': 2026,
            'num_slots': 1, 'slot1_label': 'FIRST ON CALL', 'slot1_staff': [self.staff.pk],
            'slot1_mode': 'rotate', 'slot2_mode': 'fixed', 'slot3_mode': 'fixed',
            'slot1_days_pattern': 'all', 'slot2_days_pattern': 'all', 'slot3_days_pattern': 'all',
            'ptech_active_shifts': ['M'], 'pharm_active_shifts': ['M'],
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        roster = Roster.objects.get(pk=resp.json()['id'])
        self.assertEqual(roster.entries.count(), 30)

    def test_generate_validation(self):
        resp = self.client.post(reverse('roster_generate'), {'roster_type': 'CALL'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('unit', resp.json()['errors'])

    def test_roster_export(self):
        for r in (self.roster, self.ptech_roster):
            resp = self.client.get(reverse('roster_export', args=[r.pk]))
            self.assertEqual(resp.status_code, 200)
            self.assertIn('spreadsheetml', resp['Content-Type'])

    def test_entry_update(self):
        resp = self.client.get(reverse('entry_update', args=[self.entry.pk]))
        self.assertEqual(resp.status_code, 405)
        resp = self.client.post(reverse('entry_update', args=[self.entry.pk]), {'slot1': self.staff.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['slot1'], self.staff.display_name)

    def test_ptech_entry_update(self):
        url = reverse('ptech_entry_update', args=[self.ptech_entry.pk])
        resp = self.client.post(url, {'shift': 'A'})
        self.assertEqual(resp.json()['shift'], 'A')
        self.assertEqual(self.client.post(url, {'shift': 'ZZ'}).status_code, 400)

    def test_availability(self):
        url = reverse('staff_availability', args=[self.staff.pk])
        bad = self.client.post(url, {'start_date': '2026-07-10', 'end_date': '2026-07-01'})
        self.assertEqual(bad.status_code, 400)
        self.assertIn('__all__', bad.json()['errors'])
        self.assertEqual(self.client.post(url, {'start_date': '2026-07-10', 'end_date': '2026-07-11'}).status_code, 201)
        resp = self.client.delete(reverse('staff_availability_delete', args=[self.avail.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_log_access_grant(self):
        plain = get_user_model().objects.create_user('08022222222', 'pw')
        resp = self.client.post(reverse('manage_activity_log_access'), {'user_id': plain.pk, 'action': 'grant'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(get_user_model().objects.get(pk=plain.pk).has_perm('roster.can_view_activity_log'))

    def test_auth(self):
        self.client.logout()
        self.get_json('dashboard', expect=401)
        self.get_json('me', expect=401)
        self.assertEqual(self.client.post(reverse('login'), {'phone_number': '08000000000', 'password': 'bad'}).status_code, 400)
        resp = self.client.post(reverse('login'), {'phone_number': '08000000000', 'password': 'pw'})
        self.assertTrue(resp.json()['is_admin'])
        self.get_json('dashboard')
        self.client.post(reverse('logout'))
        resp = self.client.post(reverse('register'), {'phone_number': '08033333333', 'password1': 'longpassword',
                                                      'password2': 'longpassword'})
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(resp.json()['is_admin'])
