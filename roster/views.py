"""JSON API behind the single-page frontend in web/.

Every screen of the old server-rendered UI has an endpoint here; validation
still goes through the Django forms in forms.py, posted as form data.
"""
import calendar
import functools
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import dateformat, timezone
from django.views.decorators.csrf import ensure_csrf_cookie

from .forms import (CURRENT_YEAR, DepartmentForm, HospitalForm, RosterGenerateForm,
                    StaffAvailabilityForm, StaffForm, UnitForm)
from .models import (ActivityLog, Department, Hospital, PtechStaffEntry, Roster, RosterEntry,
                     Staff, StaffAvailability, Unit, PTECH_SHIFT_CHOICES)
from .utils import (export_ptech_to_excel, export_roster_to_excel,
                    generate_ptech_roster_entries, generate_roster_entries)


@ensure_csrf_cookie
def spa(request):
    """The frontend shell; the CSRF cookie it sets is what the JS posts back."""
    return FileResponse(open(settings.BASE_DIR / 'web' / 'index.html', 'rb'), content_type='text/html')


# ── Helpers ───────────────────────────────────────────────────────────────────

def log_activity(request, action, object_type, object_str):
    ActivityLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        object_type=object_type,
        object_str=str(object_str)[:300],
    )


def is_admin(user):
    return user.is_superuser or user.is_staff


def can_view_log(user):
    return is_admin(user) or user.has_perm('roster.can_view_activity_log')


def error(message, status):
    return JsonResponse({'error': message}, status=status)


def form_errors(form):
    return JsonResponse({'errors': {k: [str(m) for m in v] for k, v in form.errors.items()}}, status=400)


def api_login(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error('Authentication required.', 401)
        return view(request, *args, **kwargs)
    return wrapper


def api_admin(view):
    @functools.wraps(view)
    @api_login
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            return error('Admin access required.', 403)
        return view(request, *args, **kwargs)
    return wrapper


def paginate(request, qs, per_page, ser):
    page = Paginator(qs, per_page).get_page(request.GET.get('page'))
    return {
        'results': [ser(o) for o in page],
        'page': page.number,
        'num_pages': page.paginator.num_pages,
        'count': page.paginator.count,
    }


def fmt(ts, pattern):
    return dateformat.format(timezone.localtime(ts), pattern)


def int_or_none(v):
    return int(v) if v and str(v).isdigit() else None


# ── Serializers ───────────────────────────────────────────────────────────────

def hospital_json(h):
    return {'id': h.pk, 'name': h.name, 'address': h.address, 'str': str(h)}


def department_json(d):
    return {'id': d.pk, 'department_name': d.department_name, 'hospital': d.hospital_id,
            'hospital_name': d.hospital.name, 'str': str(d)}


def unit_json(u):
    return {'id': u.pk, 'unit_name': u.unit_name, 'department': u.department_id,
            'department_name': u.department.department_name,
            'hospital': u.department.hospital_id, 'hospital_name': u.department.hospital.name,
            'str': str(u)}


def staff_json(s):
    return {'id': s.pk, 'unit': s.unit_id, 'staff_type': s.staff_type, 'title': s.title,
            'name': s.name, 'phone_number': s.phone_number, 'is_active': s.is_active,
            'display_name': s.display_name, 'str': str(s),
            'unit_name': s.unit.unit_name, 'department_name': s.unit.department.department_name,
            'hospital_name': s.unit.department.hospital.name}


def log_json(log, pattern):
    return {'time': fmt(log.timestamp, pattern), 'user': str(log.user) if log.user else None,
            'action': log.action, 'object_type': log.object_type, 'object_str': log.object_str}


def roster_json(r):
    return {'id': r.pk, 'str': str(r), 'roster_title': r.roster_title, 'unit_name': r.unit.unit_name,
            'period': f'{r.get_month_display()} {r.year}', 'month_display': r.get_month_display(),
            'year': r.year, 'roster_type': r.roster_type, 'num_slots': r.num_slots}


def item_view(model, form_cls, ser, obj_type, write_ok):
    """GET one record; POST form data to update it; DELETE to remove it."""
    @api_login
    def view(request, pk):
        obj = get_object_or_404(model, pk=pk)
        if request.method == 'GET':
            return JsonResponse(ser(obj))
        if not write_ok(request.user):
            return error('Admin access required.', 403)
        if request.method == 'DELETE':
            log_activity(request, 'deleted', obj_type, obj)
            obj.delete()
            return JsonResponse({'ok': True})
        if request.method == 'POST' and form_cls:
            form = form_cls(request.POST, instance=obj)
            if not form.is_valid():
                return form_errors(form)
            form.save()
            log_activity(request, 'updated', obj_type, obj)
            return JsonResponse(ser(obj))
        return error('Method not allowed.', 405)
    return view


def create(request, form_cls, ser, obj_type):
    form = form_cls(request.POST)
    if not form.is_valid():
        return form_errors(form)
    obj = form.save()
    log_activity(request, 'created', obj_type, obj)
    return JsonResponse(ser(obj), status=201)


# ── Lookups & dashboard ───────────────────────────────────────────────────────

@api_login
def lookups(request):
    """Hospitals, departments and units for filter bars and select boxes."""
    return JsonResponse({
        'hospitals': [hospital_json(h) for h in Hospital.objects.all()],
        'departments': [department_json(d) for d in Department.objects.select_related('hospital')],
        'units': [unit_json(u) for u in Unit.objects.select_related('department__hospital')],
    })


@api_login
def dashboard(request):
    departments = Department.objects.select_related('hospital').prefetch_related('units').annotate(
        active_staff_count=Count('units__staff', filter=Q(units__staff__is_active=True))
    )
    recent = Roster.objects.select_related('unit__department__hospital').order_by('-created_at')[:5]
    return JsonResponse({
        'total_hospitals': Hospital.objects.count(),
        'total_departments': Department.objects.count(),
        'total_units': Unit.objects.count(),
        'total_staff': Staff.objects.filter(is_active=True).count(),
        'total_rosters': Roster.objects.count(),
        'recent_rosters': [roster_json(r) for r in recent],
        'departments': [{'department_name': d.department_name, 'active_staff_count': d.active_staff_count,
                         'units': [u.unit_name for u in d.units.all()]} for d in departments],
        'recent_activity': [log_json(l, 'd M H:i') for l in
                            ActivityLog.objects.select_related('user').order_by('-timestamp')[:10]],
    })


# ── Activity log ──────────────────────────────────────────────────────────────

@api_login
def activity_log(request):
    if not can_view_log(request.user):
        return error('You do not have permission to view the activity log.', 403)
    logs = ActivityLog.objects.select_related('user').order_by('-timestamp')
    if request.GET.get('action'):
        logs = logs.filter(action=request.GET['action'])
    if request.GET.get('object_type'):
        logs = logs.filter(object_type=request.GET['object_type'])
    data = paginate(request, logs, 25, lambda l: log_json(l, 'd M Y H:i'))
    data['object_types'] = list(ActivityLog.objects.values_list('object_type', flat=True)
                                .distinct().order_by('object_type'))
    return JsonResponse(data)


@api_admin
def manage_activity_log_access(request):
    User = get_user_model()
    try:
        permission = Permission.objects.get(codename='can_view_activity_log')
    except Permission.DoesNotExist:
        return error('Permission not found. Run migrations first.', 500)

    if request.method == 'POST':
        try:
            target = User.objects.get(pk=int_or_none(request.POST.get('user_id')))
        except User.DoesNotExist:
            return error('User not found.', 404)
        action = request.POST.get('action')
        if action == 'grant':
            target.user_permissions.add(permission)
            return JsonResponse({'message': f'Activity log access granted to {target}.'})
        if action == 'revoke':
            target.user_permissions.remove(permission)
            return JsonResponse({'message': f'Activity log access revoked from {target}.'})
        return error('Unknown action.', 400)

    with_access = set(permission.user_set.values_list('pk', flat=True))
    return JsonResponse({'users': [
        {'id': u.pk, 'name': u.full_name or u.phone_number,
         'role': 'superuser' if u.is_superuser else 'staff' if u.is_staff else 'user',
         'has_access': u.pk in with_access}
        for u in User.objects.all().order_by('full_name')
    ]})


# ── Hospital ──────────────────────────────────────────────────────────────────

@api_login
def hospital_list(request):
    if request.method == 'POST':
        if not is_admin(request.user):
            return error('Admin access required.', 403)
        return create(request, HospitalForm, hospital_json, 'Hospital')
    hospitals = Hospital.objects.annotate(
        dept_count=Count('departments'),
        staff_count=Count('departments__units__staff', distinct=True),
    ).prefetch_related('departments').order_by('name')
    return JsonResponse(paginate(request, hospitals, 10, lambda h: {
        **hospital_json(h), 'dept_count': h.dept_count, 'staff_count': h.staff_count,
        'departments': [d.department_name for d in h.departments.all()[:3]],
    }))


def hospital_detail_json(h):
    units = Unit.objects.annotate(staff_count=Count('staff', distinct=True),
                                  roster_count=Count('rosters', distinct=True))
    departments = h.departments.prefetch_related(Prefetch('units', queryset=units)).annotate(
        unit_count=Count('units'),
        staff_count=Count('units__staff', filter=Q(units__staff__is_active=True), distinct=True),
    )
    return {**hospital_json(h), 'departments': [
        {'id': d.pk, 'department_name': d.department_name, 'unit_count': d.unit_count,
         'staff_count': d.staff_count,
         'units': [{'id': u.pk, 'unit_name': u.unit_name, 'staff_count': u.staff_count,
                    'roster_count': u.roster_count} for u in d.units.all()]}
        for d in departments
    ]}


hospital_detail = item_view(Hospital, HospitalForm, hospital_detail_json, 'Hospital', is_admin)


# ── Department ────────────────────────────────────────────────────────────────

@api_login
def department_list(request):
    if request.method == 'POST':
        if not is_admin(request.user):
            return error('Admin access required.', 403)
        return create(request, DepartmentForm, department_json, 'Department')
    departments = Department.objects.select_related('hospital').prefetch_related('units').annotate(
        unit_count=Count('units'),
    ).order_by('hospital__name', 'department_name')
    hospital_id = int_or_none(request.GET.get('hospital'))
    if hospital_id:
        departments = departments.filter(hospital_id=hospital_id)
    return JsonResponse(paginate(request, departments, 10, lambda d: {
        **department_json(d), 'unit_count': d.unit_count,
        'units': [{'id': u.pk, 'unit_name': u.unit_name} for u in d.units.all()],
    }))


department_detail = item_view(Department, DepartmentForm, department_json, 'Department', is_admin)


# ── Unit ──────────────────────────────────────────────────────────────────────

@api_login
def unit_list(request):
    if request.method == 'POST':
        if not is_admin(request.user):
            return error('Admin access required.', 403)
        return create(request, UnitForm, unit_json, 'Unit')
    units = Unit.objects.select_related('department__hospital').annotate(
        staff_count=Count('staff', filter=Q(staff__is_active=True), distinct=True),
        roster_count=Count('rosters', distinct=True),
    ).order_by('department__hospital__name', 'unit_name')
    hospital_id = int_or_none(request.GET.get('hospital'))
    dept_id = int_or_none(request.GET.get('dept'))
    if hospital_id:
        units = units.filter(department__hospital_id=hospital_id)
    if dept_id:
        units = units.filter(department_id=dept_id)
    return JsonResponse(paginate(request, units, 10, lambda u: {
        **unit_json(u), 'staff_count': u.staff_count, 'roster_count': u.roster_count,
    }))


unit_detail = item_view(Unit, UnitForm, unit_json, 'Unit', is_admin)


# ── Staff ─────────────────────────────────────────────────────────────────────

@api_login
def staff_list(request):
    if request.method == 'POST':
        return create(request, StaffForm, staff_json, 'Staff')
    staff = Staff.objects.select_related('unit__department__hospital').all()
    hospital_id = int_or_none(request.GET.get('hospital'))
    dept_id = int_or_none(request.GET.get('dept'))
    unit_id = int_or_none(request.GET.get('unit'))
    if hospital_id:
        staff = staff.filter(unit__department__hospital_id=hospital_id)
    if dept_id:
        staff = staff.filter(unit__department_id=dept_id)
    if unit_id:
        staff = staff.filter(unit_id=unit_id)
    return JsonResponse(paginate(request, staff, 15, staff_json))


staff_detail = item_view(Staff, StaffForm, staff_json, 'Staff', lambda user: True)


@api_login
def staff_availability(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    if request.method == 'POST':
        form = StaffAvailabilityForm(request.POST)
        if not form.is_valid():
            return form_errors(form)
        av = form.save(commit=False)
        av.staff = staff
        av.save()
        log_activity(request, 'created', 'StaffAvailability', f'{staff} unavailable {av.start_date}→{av.end_date}')
        return JsonResponse({'ok': True}, status=201)
    return JsonResponse({'staff': staff_json(staff), 'records': [
        {'id': r.pk, 'start': r.start_date.strftime('%d %b %Y'), 'end': r.end_date.strftime('%d %b %Y'),
         'reason': r.reason}
        for r in staff.availability_records.order_by('start_date')
    ]})


@api_login
def staff_availability_delete(request, pk):
    if request.method != 'DELETE':
        return error('Method not allowed.', 405)
    record = get_object_or_404(StaffAvailability, pk=pk)
    log_activity(request, 'deleted', 'StaffAvailability', record)
    record.delete()
    return JsonResponse({'ok': True})


# ── Roster ────────────────────────────────────────────────────────────────────

@api_login
def roster_list(request):
    rosters = Roster.objects.select_related('unit__department__hospital').annotate(
        entries_count=Count('entries', distinct=True),
        ptech_entries_count=Count('ptech_entries', distinct=True),
    ).order_by('-year', '-month')
    return JsonResponse(paginate(request, rosters, 10, lambda r: {
        **roster_json(r), 'created': fmt(r.created_at, 'M d, Y'),
        'entries_count': r.ptech_entries_count if r.roster_type == 'PTECH' else r.entries_count,
    }))


def roster_detail_json(roster):
    staff_type = 'PTECH' if roster.roster_type == 'PTECH' else 'PHARM'
    all_staff = Staff.objects.filter(unit=roster.unit, is_active=True, staff_type=staff_type)
    unit = roster.unit
    data = {
        **roster_json(roster),
        'hospital_name': unit.department.hospital.name,
        'department_name': unit.department.department_name,
        'month_year_display': roster.month_year_display,
        'shift_config_display': roster.get_shift_config_display() if roster.shift_config else '',
        'slot_labels': [roster.slot1_label, roster.slot2_label, roster.slot3_label],
        'all_staff': [{'id': s.pk, 'display_name': s.display_name, 'phone_number': s.phone_number}
                      for s in all_staff],
        'is_ptech': roster.roster_type in ('PTECH', 'PHARM_SHIFT'),
    }

    if data['is_ptech']:
        _, num_days = calendar.monthrange(roster.year, roster.month)
        dates = [date(roster.year, roster.month, d) for d in range(1, num_days + 1)]
        rows = {}
        for e in roster.ptech_entries.select_related('staff').order_by('staff__name', 'date'):
            row = rows.setdefault(e.staff_id, {'staff': e.staff.display_name, 'cells': [None] * num_days})
            row['cells'][e.date.day - 1] = {'id': e.pk, 'shift': e.shift}
        data['dates'] = [{'day': d.day, 'dow': d.strftime('%a').upper(), 'weekend': d.weekday() >= 5,
                          'title': d.strftime('%a %d %b')} for d in dates]
        data['rows'] = list(rows.values())
        return data

    person = lambda s: {'id': s.pk, 'name': s.display_name} if s else None
    data['entries'] = [
        {'id': e.pk, 'day_abbr': e.day_abbr, 'date_display': e.date_display, 'weekend': e.date.weekday() >= 5,
         'slots': [person(e.slot1), person(e.slot2), person(e.slot3)]}
        for e in roster.entries.select_related('slot1', 'slot2', 'slot3').order_by('date')
    ]
    return data


roster_detail = item_view(Roster, None, roster_detail_json, 'Roster', lambda user: True)


def generate_options():
    pool = lambda kind: [{'id': s.pk, 'str': str(s), 'unit': s.unit_id}
                         for s in Staff.objects.filter(is_active=True, staff_type=kind)]
    return {
        'units': [{'id': u.pk, 'str': str(u), 'department': u.department_id}
                  for u in Unit.objects.select_related('department__hospital')],
        'departments': [{'id': d.pk, 'label': f'{d.hospital.name} / {d.department_name}'}
                        for d in Department.objects.select_related('hospital')],
        'pharm': pool('PHARM'),
        'ptech': pool('PTECH'),
        'current_year': CURRENT_YEAR,
    }


@api_login
def roster_generate(request):
    if request.method != 'POST':
        return JsonResponse(generate_options())
    form = RosterGenerateForm(request.POST)
    if not form.is_valid():
        return form_errors(form)

    cd = form.cleaned_data
    unit = cd['unit']
    month = int(cd['month'])
    year = int(cd['year'])
    num_slots = int(cd['num_slots'])

    def collect_start_dates(pairs):
        """{staff_id: earliest in-month start date} from `<prefix>_start_<id>` POST fields."""
        out = {}
        for prefix, pool in pairs:
            for s in pool or []:
                raw = (request.POST.get(f'{prefix}_start_{s.id}') or '').strip()
                if not raw:
                    continue
                try:
                    sd = date.fromisoformat(raw)
                except ValueError:
                    continue
                if sd.month == month and sd.year == year:  # only mid-month starts matter
                    if s.id not in out or sd < out[s.id]:
                        out[s.id] = sd
        return out

    Roster.objects.filter(unit=unit, month=month, year=year).delete()

    roster_data = {
        'unit': unit,
        'roster_title': cd['roster_title'],
        'month': month,
        'year': year,
        'roster_type': cd['roster_type'],
    }

    if cd['roster_type'] in ('PTECH', 'PHARM_SHIFT'):
        roster_data['num_slots'] = 1
        roster_data['slot1_label'] = 'MORNING'
        roster_data['slot2_label'] = 'AFTERNOON'
        roster_data['slot3_label'] = 'OFF'
    else:
        roster_data['num_slots'] = num_slots
        roster_data['slot1_label'] = cd['slot1_label']
        roster_data['slot2_label'] = cd.get('slot2_label') or 'SECOND ON CALL'
        roster_data['slot3_label'] = cd.get('slot3_label') or 'THIRD ON CALL'

    roster = Roster.objects.create(**roster_data)

    if cd['roster_type'] == 'PTECH':
        generate_ptech_roster_entries(
            roster,
            morning_staff=cd.get('ptech_morning_staff') or [],
            afternoon_staff=cd.get('ptech_afternoon_staff') or [],
            cm_staff=cd.get('ptech_cm_staff') or [],
            staff_start_dates=collect_start_dates((
                ('ptech_morning', cd.get('ptech_morning_staff')),
                ('ptech_afternoon', cd.get('ptech_afternoon_staff')),
                ('ptech_cm', cd.get('ptech_cm_staff')),
            )),
            post_cm_rest_days=int(cd.get('ptech_post_cm_rest') or 0),
            rotate_shifts=bool(cd.get('ptech_rotate_shifts')),
            cm_min_gap=int(cd.get('ptech_cm_min_gap') or 0),
            morning_work_days=int(cd.get('ptech_morning_work_days') or 5),
            morning_off_days=int(cd.get('ptech_morning_off_days') or 0),
            afternoon_work_days=int(cd.get('ptech_afternoon_work_days') or 5),
            afternoon_off_days=int(cd.get('ptech_afternoon_off_days') or 0),
            night_work_days=int(cd.get('ptech_night_work_days') or 2),
            night_off_days=int(cd.get('ptech_night_off_days') or 5),
            active_shifts=cd.get('ptech_active_shifts') or ['M', 'A', 'N'],
        )
    elif cd['roster_type'] == 'PHARM_SHIFT':
        generate_ptech_roster_entries(
            roster,
            morning_staff=cd.get('pharm_morning_staff') or [],
            afternoon_staff=cd.get('pharm_afternoon_staff') or [],
            cm_staff=cd.get('pharm_night_staff') or [],
            staff_start_dates=collect_start_dates((
                ('pharm_morning', cd.get('pharm_morning_staff')),
                ('pharm_afternoon', cd.get('pharm_afternoon_staff')),
                ('pharm_night', cd.get('pharm_night_staff')),
            )),
            post_cm_rest_days=0,
            rotate_shifts=bool(cd.get('pharm_rotate_shifts')),
            cm_min_gap=int(cd.get('pharm_night_min_gap') or 0),
            morning_work_days=int(cd.get('pharm_morning_work_days') or 5),
            morning_off_days=int(cd.get('pharm_morning_off_days') or 2),
            afternoon_work_days=int(cd.get('pharm_afternoon_work_days') or 5),
            afternoon_off_days=int(cd.get('pharm_afternoon_off_days') or 2),
            night_work_days=int(cd.get('pharm_night_work_days') or 2),
            night_off_days=int(cd.get('pharm_night_off_days') or 5),
            active_shifts=cd.get('pharm_active_shifts') or ['M', 'A', 'N'],
        )
    else:
        # Per-staff cap on first-on-call (slot1) appearances; blank = unlimited
        slot1_quota = {}
        for s in cd['slot1_staff']:
            raw = (request.POST.get(f'slot1_count_{s.id}') or '').strip()
            if raw.isdigit() and int(raw) > 0:
                slot1_quota[s.id] = int(raw)

        # Per-staff "include from" date; excludes staff on days before it
        staff_start_dates = collect_start_dates((
            ('slot1', cd['slot1_staff']),
            ('slot2', cd.get('slot2_staff')),
            ('slot3', cd.get('slot3_staff')),
        ))

        generate_roster_entries(
            roster,
            slot1_staff=cd['slot1_staff'],
            slot2_staff=cd.get('slot2_staff') or [],
            slot3_staff=cd.get('slot3_staff') or [],
            slot1_mode=cd['slot1_mode'],
            slot2_mode=cd['slot2_mode'],
            slot3_mode=cd['slot3_mode'],
            slot1_days_pattern=cd.get('slot1_days_pattern', 'all'),
            slot1_custom_days=cd.get('slot1_custom_days') or [],
            slot1_min_gap=cd.get('slot1_min_gap') or 0,
            slot2_days_pattern=cd.get('slot2_days_pattern', 'all'),
            slot2_custom_days=cd.get('slot2_custom_days') or [],
            slot2_min_gap=cd.get('slot2_min_gap') or 0,
            slot3_days_pattern=cd.get('slot3_days_pattern', 'all'),
            slot3_custom_days=cd.get('slot3_custom_days') or [],
            slot3_min_gap=cd.get('slot3_min_gap') or 0,
            slot1_quota=slot1_quota,
            staff_start_dates=staff_start_dates,
        )

    log_activity(request, 'generated', 'Roster', roster)
    return JsonResponse({'id': roster.pk, 'message': f'Roster for {calendar.month_name[month]} {year} generated.'},
                        status=201)


@api_login
def roster_export(request, pk):
    roster = get_object_or_404(Roster, pk=pk)
    log_activity(request, 'exported', 'Roster', roster)
    if roster.roster_type in ('PTECH', 'PHARM_SHIFT'):
        xlsx = export_ptech_to_excel(roster)
    else:
        xlsx = export_roster_to_excel(roster)
    filename = f"Roster_{calendar.month_name[roster.month]}_{roster.year}.xlsx"
    response = HttpResponse(
        xlsx.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_login
def entry_update(request, pk):
    if request.method != 'POST':
        return error('POST only', 405)
    entry = get_object_or_404(RosterEntry, pk=pk)
    roster = entry.roster

    def get_staff(field):
        sid = request.POST.get(field)
        if sid:
            try:
                return Staff.objects.get(pk=int(sid))
            except (Staff.DoesNotExist, ValueError):
                pass
        return None

    entry.slot1 = get_staff('slot1')
    if roster.num_slots >= 2:
        entry.slot2 = get_staff('slot2')
    if roster.num_slots >= 3:
        entry.slot3 = get_staff('slot3')
    entry.save()

    return JsonResponse({
        'slot1': entry.slot1.display_name if entry.slot1 else '',
        'slot2': entry.slot2.display_name if entry.slot2 else '',
        'slot3': entry.slot3.display_name if entry.slot3 else '',
    })


@api_login
def ptech_entry_update(request, pk):
    if request.method != 'POST':
        return error('POST only', 405)
    entry = get_object_or_404(PtechStaffEntry, pk=pk)
    shift = request.POST.get('shift', '').upper()
    if shift not in {code for code, _ in PTECH_SHIFT_CHOICES}:
        return error(f'Invalid shift code: {shift}', 400)
    entry.shift = shift
    entry.save()
    return JsonResponse({'shift': entry.shift})
