import calendar
import functools

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Permission
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator

from .forms import DepartmentForm, HospitalForm, RosterGenerateForm, StaffAvailabilityForm, StaffForm, UnitForm
from .models import (ActivityLog, Department, Hospital, Roster, RosterEntry, Staff,
                     StaffAvailability, Unit, PTECH_SHIFT_CHOICES)
from .models import PtechStaffEntry
from .utils import (export_ptech_to_excel, export_roster_to_excel,
                    generate_ptech_roster_entries, generate_roster_entries)


def log_activity(request, action, object_type, object_str):
    ActivityLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        object_type=object_type,
        object_str=str(object_str)[:300],
    )


def admin_required(view_func):
    @functools.wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    ctx = {
        'total_hospitals': Hospital.objects.count(),
        'total_departments': Department.objects.count(),
        'total_units': Unit.objects.count(),
        'total_staff': Staff.objects.filter(is_active=True).count(),
        'total_rosters': Roster.objects.count(),
        'recent_rosters': Roster.objects.select_related('unit__department__hospital').order_by('-created_at')[:5],
        'departments': Department.objects.select_related('hospital').prefetch_related('units').annotate(
            active_staff_count=Count('units__staff', filter=Q(units__staff__is_active=True))
        ),
        'recent_activity': ActivityLog.objects.select_related('user').order_by('-timestamp')[:10],
    }
    return render(request, 'roster/dashboard.html', ctx)


@login_required
def activity_log(request):
    if not (request.user.is_superuser or request.user.is_staff or
            request.user.has_perm('roster.can_view_activity_log')):
        messages.error(request, 'You do not have permission to view the activity log.')
        return redirect('dashboard')
    logs = ActivityLog.objects.select_related('user').order_by('-timestamp')
    action_filter = request.GET.get('action', '')
    object_filter = request.GET.get('object_type', '')
    if action_filter:
        logs = logs.filter(action=action_filter)
    if object_filter:
        logs = logs.filter(object_type=object_filter)
    paginator = Paginator(logs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    object_types = ActivityLog.objects.values_list('object_type', flat=True).distinct().order_by('object_type')
    return render(request, 'roster/activity_log.html', {
        'page_obj': page_obj,
        'action_filter': action_filter,
        'object_filter': object_filter,
        'object_types': object_types,
    })


@login_required
def manage_activity_log_access(request):
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, 'Admin access required.')
        return redirect('dashboard')

    User = get_user_model()
    try:
        permission = Permission.objects.get(codename='can_view_activity_log')
    except Permission.DoesNotExist:
        messages.error(request, 'Permission not found. Run migrations first.')
        return redirect('dashboard')

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        try:
            target_user = User.objects.get(pk=user_id)
            if action == 'grant':
                target_user.user_permissions.add(permission)
                messages.success(request, f'Activity log access granted to {target_user}.')
            elif action == 'revoke':
                target_user.user_permissions.remove(permission)
                messages.success(request, f'Activity log access revoked from {target_user}.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
        return redirect('manage_activity_log_access')

    users = User.objects.all().order_by('full_name')
    users_with_access = set(permission.user_set.values_list('pk', flat=True))
    return render(request, 'roster/manage_activity_log_access.html', {
        'users': users,
        'users_with_access': users_with_access,
    })


# ── Hospital ──────────────────────────────────────────────────────────────────

@login_required
def hospital_list(request):
    hospitals = Hospital.objects.annotate(
        dept_count=Count('departments'),
        staff_count=Count('departments__units__staff', distinct=True),
    )
    paginator = Paginator(hospitals, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'roster/hospital_list.html', {'page_obj': page_obj})


@admin_required
def hospital_create(request):
    form = HospitalForm(request.POST or None)
    if form.is_valid():
        hospital = form.save()
        log_activity(request, 'created', 'Hospital', hospital)
        messages.success(request, 'Hospital created.')
        return redirect('hospital_list')
    return render(request, 'roster/hospital_form.html', {'form': form, 'title': 'Add Hospital'})


@admin_required
def hospital_edit(request, pk):
    hospital = get_object_or_404(Hospital, pk=pk)
    form = HospitalForm(request.POST or None, instance=hospital)
    if form.is_valid():
        form.save()
        log_activity(request, 'updated', 'Hospital', hospital)
        messages.success(request, 'Hospital updated.')
        return redirect('hospital_list')
    return render(request, 'roster/hospital_form.html', {'form': form, 'title': 'Edit Hospital', 'obj': hospital})


@admin_required
def hospital_delete(request, pk):
    hospital = get_object_or_404(Hospital, pk=pk)
    if request.method == 'POST':
        log_activity(request, 'deleted', 'Hospital', hospital)
        hospital.delete()
        messages.success(request, 'Hospital deleted.')
        return redirect('hospital_list')
    return render(request, 'roster/confirm_delete.html', {'obj': hospital, 'obj_type': 'Hospital'})


@login_required
def hospital_detail(request, pk):
    hospital = get_object_or_404(Hospital, pk=pk)
    departments = hospital.departments.prefetch_related('units__staff').annotate(
        unit_count=Count('units'),
        staff_count=Count('units__staff', filter=Q(units__staff__is_active=True), distinct=True),
    )
    return render(request, 'roster/hospital_detail.html', {
        'hospital': hospital,
        'departments': departments,
    })


# ── Department ────────────────────────────────────────────────────────────────

@login_required
def department_list(request):
    hospital_id = request.GET.get('hospital')
    departments = Department.objects.select_related('hospital').prefetch_related('units').annotate(
        unit_count=Count('units'),
        staff_count=Count('units__staff', filter=Q(units__staff__is_active=True), distinct=True),
    )
    hospitals = Hospital.objects.all()
    if hospital_id:
        departments = departments.filter(hospital_id=hospital_id)
    paginator = Paginator(departments, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'roster/department_list.html', {
        'page_obj': page_obj,
        'hospitals': hospitals,
        'selected_hospital': int(hospital_id) if hospital_id else None,
    })


@admin_required
def department_create(request):
    hospital_id = request.GET.get('hospital')
    form = DepartmentForm(request.POST or None, hospital_id=hospital_id)
    if form.is_valid():
        dept = form.save()
        log_activity(request, 'created', 'Department', dept)
        messages.success(request, 'Department created.')
        return redirect('department_list')
    return render(request, 'roster/department_form.html', {'form': form, 'title': 'Add Department'})


@admin_required
def department_edit(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    form = DepartmentForm(request.POST or None, instance=dept)
    if form.is_valid():
        form.save()
        log_activity(request, 'updated', 'Department', dept)
        messages.success(request, 'Department updated.')
        return redirect('department_list')
    return render(request, 'roster/department_form.html', {'form': form, 'title': 'Edit Department', 'obj': dept})


@admin_required
def department_delete(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        log_activity(request, 'deleted', 'Department', dept)
        dept.delete()
        messages.success(request, 'Department deleted.')
        return redirect('department_list')
    return render(request, 'roster/confirm_delete.html', {'obj': dept, 'obj_type': 'Department'})


# ── Unit ──────────────────────────────────────────────────────────────────────

@login_required
def unit_list(request):
    dept_id = request.GET.get('dept')
    hospital_id = request.GET.get('hospital')
    units = Unit.objects.select_related('department__hospital').prefetch_related('staff').annotate(
        staff_count=Count('staff', filter=Q(staff__is_active=True), distinct=True),
        roster_count=Count('rosters'),
    )
    hospitals = Hospital.objects.all()
    departments = Department.objects.select_related('hospital').all()
    if hospital_id:
        departments = departments.filter(hospital_id=hospital_id)
        units = units.filter(department__hospital_id=hospital_id)
    if dept_id:
        units = units.filter(department_id=dept_id)
    paginator = Paginator(units, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'roster/unit_list.html', {
        'page_obj': page_obj,
        'hospitals': hospitals,
        'departments': departments,
        'selected_dept': int(dept_id) if dept_id else None,
        'selected_hospital': int(hospital_id) if hospital_id else None,
    })


@admin_required
def unit_create(request):
    dept_id = request.GET.get('dept')
    form = UnitForm(request.POST or None, department_id=dept_id)
    if form.is_valid():
        unit = form.save()
        log_activity(request, 'created', 'Unit', unit)
        messages.success(request, 'Unit created.')
        return redirect('unit_list')
    return render(request, 'roster/unit_form.html', {'form': form, 'title': 'Add Unit'})


@admin_required
def unit_edit(request, pk):
    unit = get_object_or_404(Unit, pk=pk)
    form = UnitForm(request.POST or None, instance=unit)
    if form.is_valid():
        form.save()
        log_activity(request, 'updated', 'Unit', unit)
        messages.success(request, 'Unit updated.')
        return redirect('unit_list')
    return render(request, 'roster/unit_form.html', {'form': form, 'title': 'Edit Unit', 'obj': unit})


@admin_required
def unit_delete(request, pk):
    unit = get_object_or_404(Unit, pk=pk)
    if request.method == 'POST':
        log_activity(request, 'deleted', 'Unit', unit)
        unit.delete()
        messages.success(request, 'Unit deleted.')
        return redirect('unit_list')
    return render(request, 'roster/confirm_delete.html', {'obj': unit, 'obj_type': 'Unit'})


# ── Staff ─────────────────────────────────────────────────────────────────────

@login_required
def staff_list(request):
    unit_id = request.GET.get('unit')
    dept_id = request.GET.get('dept')
    hospital_id = request.GET.get('hospital')
    staff_qs = Staff.objects.select_related('unit__department__hospital').all()
    if hospital_id:
        staff_qs = staff_qs.filter(unit__department__hospital_id=hospital_id)
    if dept_id:
        staff_qs = staff_qs.filter(unit__department_id=dept_id)
    if unit_id:
        staff_qs = staff_qs.filter(unit_id=unit_id)
    hospitals = Hospital.objects.all()
    departments = Department.objects.select_related('hospital').all()
    units = Unit.objects.select_related('department').all()
    if hospital_id:
        departments = departments.filter(hospital_id=hospital_id)
        units = units.filter(department__hospital_id=hospital_id)
    if dept_id:
        units = units.filter(department_id=dept_id)
    paginator = Paginator(staff_qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'roster/staff_list.html', {
        'page_obj': page_obj,
        'hospitals': hospitals,
        'departments': departments,
        'units': units,
        'selected_unit': int(unit_id) if unit_id else None,
        'selected_dept': int(dept_id) if dept_id else None,
        'selected_hospital': int(hospital_id) if hospital_id else None,
    })


@login_required
def staff_create(request):
    unit_id = request.GET.get('unit')
    form = StaffForm(request.POST or None, unit_id=unit_id)
    if form.is_valid():
        staff = form.save()
        log_activity(request, 'created', 'Staff', staff)
        messages.success(request, f'{staff} added.')
        return redirect('staff_list')
    hospitals = Hospital.objects.all()
    departments = Department.objects.select_related('hospital').all()
    selected_hospital = None
    selected_dept = None
    if unit_id:
        try:
            unit = Unit.objects.select_related('department__hospital').get(pk=unit_id)
            selected_dept = unit.department.pk
            selected_hospital = unit.department.hospital.pk
        except Unit.DoesNotExist:
            pass
    return render(request, 'roster/staff_form.html', {
        'form': form,
        'title': 'Add Staff',
        'hospitals': hospitals,
        'departments': departments,
        'selected_hospital': selected_hospital,
        'selected_dept': selected_dept,
    })


@login_required
def staff_edit(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    form = StaffForm(request.POST or None, instance=staff)
    if form.is_valid():
        form.save()
        log_activity(request, 'updated', 'Staff', staff)
        messages.success(request, 'Staff updated.')
        return redirect('staff_list')
    hospitals = Hospital.objects.all()
    departments = Department.objects.select_related('hospital').all()
    return render(request, 'roster/staff_form.html', {
        'form': form,
        'title': 'Edit Staff',
        'obj': staff,
        'hospitals': hospitals,
        'departments': departments,
        'selected_hospital': staff.unit.department.hospital.pk,
        'selected_dept': staff.unit.department.pk,
    })


@login_required
def staff_delete(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    if request.method == 'POST':
        log_activity(request, 'deleted', 'Staff', staff)
        staff.delete()
        messages.success(request, 'Staff member deleted.')
        return redirect('staff_list')
    return render(request, 'roster/confirm_delete.html', {'obj': staff, 'obj_type': 'Staff'})


@login_required
def staff_availability(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    records = staff.availability_records.order_by('start_date')
    form = StaffAvailabilityForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        av = form.save(commit=False)
        av.staff = staff
        av.save()
        log_activity(request, 'created', 'StaffAvailability', f'{staff} unavailable {av.start_date}→{av.end_date}')
        messages.success(request, 'Unavailability period saved.')
        return redirect('staff_availability', pk=pk)
    return render(request, 'roster/staff_availability.html', {
        'staff': staff,
        'records': records,
        'form': form,
    })


@login_required
def staff_availability_delete(request, pk):
    record = get_object_or_404(StaffAvailability, pk=pk)
    staff_pk = record.staff.pk
    if request.method == 'POST':
        log_activity(request, 'deleted', 'StaffAvailability', record)
        record.delete()
        messages.success(request, 'Unavailability record removed.')
        return redirect('staff_availability', pk=staff_pk)
    return render(request, 'roster/confirm_delete.html', {'obj': record, 'obj_type': 'Unavailability Record'})


@login_required
def staff_by_department(request, dept_id):
    units = Unit.objects.filter(department_id=dept_id).values('id', 'unit_name')
    return JsonResponse({'units': list(units)})


@login_required
def staff_by_unit(request, unit_id):
    staff = Staff.objects.filter(unit_id=unit_id, is_active=True).values('id', 'title', 'name')
    return JsonResponse({'staff': list(staff)})


# ── Roster ────────────────────────────────────────────────────────────────────

@login_required
def roster_list(request):
    rosters = Roster.objects.select_related('unit__department__hospital').annotate(
        entries_count=Count('entries', distinct=True),
        ptech_entries_count=Count('ptech_entries', distinct=True),
    )
    paginator = Paginator(rosters, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'roster/roster_list.html', {'page_obj': page_obj})


@login_required
def roster_detail(request, pk):
    roster = get_object_or_404(Roster, pk=pk)
    staff_type_filter = 'PTECH' if roster.roster_type == 'PTECH' else 'PHARM'
    all_staff = Staff.objects.filter(unit=roster.unit, is_active=True, staff_type=staff_type_filter)

    if roster.roster_type in ('PTECH', 'PHARM_SHIFT'):
        _, num_days = calendar.monthrange(roster.year, roster.month)
        from datetime import date as date_cls
        ptech_dates = [date_cls(roster.year, roster.month, d) for d in range(1, num_days + 1)]

        ptech_entries = roster.ptech_entries.select_related('staff').order_by('staff__name', 'date')
        staff_order = {}
        ptech_rows = []
        for entry in ptech_entries:
            if entry.staff_id not in staff_order:
                staff_order[entry.staff_id] = len(ptech_rows)
                ptech_rows.append({
                    'staff': entry.staff,
                    'shifts': [None] * num_days,
                    'entry_ids': [None] * num_days,
                })
            idx = staff_order[entry.staff_id]
            ptech_rows[idx]['shifts'][entry.date.day - 1] = entry.shift
            ptech_rows[idx]['entry_ids'][entry.date.day - 1] = entry.pk

        for row in ptech_rows:
            row['day_data'] = list(zip(ptech_dates, row['shifts'], row['entry_ids']))

        return render(request, 'roster/roster_detail.html', {
            'roster': roster,
            'all_staff': all_staff,
            'is_ptech': True,
            'ptech_rows': ptech_rows,
            'ptech_dates': ptech_dates,
            'is_pharm_shift': roster.roster_type == 'PHARM_SHIFT',
        })

    entries = roster.entries.select_related('slot1', 'slot2', 'slot3').order_by('date')
    return render(request, 'roster/roster_detail.html', {
        'roster': roster,
        'entries': entries,
        'all_staff': all_staff,
        'is_ptech': False,
    })


@login_required
def roster_generate(request):
    departments = Department.objects.select_related('hospital').prefetch_related('units')
    form = RosterGenerateForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        unit = cd['unit']
        month = int(cd['month'])
        year = int(cd['year'])
        num_slots = int(cd['num_slots'])

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
            )

        log_activity(request, 'generated', 'Roster', roster)
        messages.success(request, f'Roster for {calendar.month_name[month]} {year} generated.')
        return redirect('roster_detail', pk=roster.pk)

    return render(request, 'roster/roster_generate.html', {'form': form, 'departments': departments})


@login_required
def roster_delete(request, pk):
    roster = get_object_or_404(Roster, pk=pk)
    if request.method == 'POST':
        log_activity(request, 'deleted', 'Roster', roster)
        roster.delete()
        messages.success(request, 'Roster deleted.')
        return redirect('roster_list')
    return render(request, 'roster/confirm_delete.html', {'obj': roster, 'obj_type': 'Roster'})


@login_required
def roster_export(request, pk):
    roster = get_object_or_404(Roster, pk=pk)
    log_activity(request, 'exported', 'Roster', roster)
    if roster.roster_type in ('PTECH', 'PHARM_SHIFT'):
        xlsx = export_ptech_to_excel(roster)
    else:
        xlsx = export_roster_to_excel(roster)
    month_name = calendar.month_name[roster.month]
    filename = f"Roster_{month_name}_{roster.year}.xlsx"
    response = HttpResponse(
        xlsx.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def entry_update(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
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


@login_required
def ptech_entry_update(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    entry = get_object_or_404(PtechStaffEntry, pk=pk)
    shift = request.POST.get('shift', '').upper()
    valid_codes = {code for code, _ in PTECH_SHIFT_CHOICES}
    if shift not in valid_codes:
        return JsonResponse({'error': f'Invalid shift code: {shift}'}, status=400)
    entry.shift = shift
    entry.save()
    return JsonResponse({'shift': entry.shift})
