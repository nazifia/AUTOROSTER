import calendar
from datetime import date
from io import BytesIO

import openpyxl
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side
)
from openpyxl.utils import get_column_letter

from datetime import timedelta

from .models import PtechStaffEntry, RosterEntry, StaffAvailability


def _build_unavailability_map(staff_ids, year, month):
    """Return {date: set(staff_id)} for unavailable staff in the given month."""
    _, num_days = calendar.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end = date(year, month, num_days)

    records = StaffAvailability.objects.filter(
        staff_id__in=staff_ids,
        start_date__lte=month_end,
        end_date__gte=month_start,
    ).values_list('staff_id', 'start_date', 'end_date')

    unavailable = {}
    for staff_id, start, end in records:
        cur = max(start, month_start)
        cutoff = min(end, month_end)
        while cur <= cutoff:
            unavailable.setdefault(cur, set()).add(staff_id)
            cur += timedelta(days=1)
    return unavailable


def _resolve_active_days(days_pattern, custom_days):
    """Return set of weekday ints (0=Mon … 6=Sun) based on pattern choice."""
    if days_pattern == 'weekdays':
        return {0, 1, 2, 3, 4}
    if days_pattern == 'weekends':
        return {5, 6}
    if days_pattern == 'custom' and custom_days:
        return {int(d) for d in custom_days}
    return {0, 1, 2, 3, 4, 5, 6}


def _pick(pool, idx, unavailable_ids, recently_assigned, current_day, min_gap, mode):
    """Pick next available staff; return (staff_or_None, new_idx)."""
    if not pool:
        return None, idx

    def eligible(s):
        if s.id in unavailable_ids:
            return False
        if min_gap and min_gap > 0:
            last = recently_assigned.get(s.id)
            if last is not None and (current_day - last) < min_gap:
                return False
        return True

    if mode == 'fixed':
        for s in pool:
            if eligible(s):
                return s, idx
        return None, idx

    for offset in range(len(pool)):
        candidate = pool[(idx + offset) % len(pool)]
        if eligible(candidate):
            return candidate, (idx + offset + 1) % len(pool)
    return None, idx


def generate_roster_entries(roster, slot1_staff, slot2_staff, slot3_staff,
                            slot1_mode='rotate', slot2_mode='rotate', slot3_mode='rotate',
                            slot1_days_pattern='all', slot1_custom_days=None, slot1_min_gap=0,
                            slot2_days_pattern='all', slot2_custom_days=None, slot2_min_gap=0,
                            slot3_days_pattern='all', slot3_custom_days=None, slot3_min_gap=0):
    """
    Generate RosterEntry objects for every day in the roster's month/year.
    Respects StaffAvailability, days patterns, and min-gap constraints.
    """
    RosterEntry.objects.filter(roster=roster).delete()

    year, month = roster.year, roster.month
    _, num_days = calendar.monthrange(year, month)

    s1_pool = list(slot1_staff)
    s2_pool = list(slot2_staff)
    s3_pool = list(slot3_staff)

    all_staff_ids = {s.id for s in s1_pool + s2_pool + s3_pool}
    unavailability = _build_unavailability_map(all_staff_ids, year, month)

    s1_active = _resolve_active_days(slot1_days_pattern, slot1_custom_days)
    s2_active = _resolve_active_days(slot2_days_pattern, slot2_custom_days)
    s3_active = _resolve_active_days(slot3_days_pattern, slot3_custom_days)

    s1_min_gap = int(slot1_min_gap or 0)
    s2_min_gap = int(slot2_min_gap or 0)
    s3_min_gap = int(slot3_min_gap or 0)

    s1_idx = s2_idx = s3_idx = 0
    s1_last = {}
    s2_last = {}
    s3_last = {}
    entries = []

    for day in range(1, num_days + 1):
        d = date(year, month, day)
        unavail = unavailability.get(d, set())
        weekday = d.weekday()

        s1 = s2 = s3 = None

        if s1_pool and weekday in s1_active:
            s1, s1_idx = _pick(s1_pool, s1_idx, unavail, s1_last, day, s1_min_gap, slot1_mode)
            if s1:
                s1_last[s1.id] = day

        if s2_pool and roster.num_slots >= 2 and weekday in s2_active:
            s2, s2_idx = _pick(s2_pool, s2_idx, unavail, s2_last, day, s2_min_gap, slot2_mode)
            if s2:
                s2_last[s2.id] = day

        if s3_pool and roster.num_slots >= 3 and weekday in s3_active:
            s3, s3_idx = _pick(s3_pool, s3_idx, unavail, s3_last, day, s3_min_gap, slot3_mode)
            if s3:
                s3_last[s3.id] = day

        entries.append(RosterEntry(roster=roster, date=d, slot1=s1, slot2=s2, slot3=s3))

    RosterEntry.objects.bulk_create(entries)


def generate_ptech_roster_entries(roster, morning_staff, afternoon_staff, cm_staff,
                                   post_cm_rest=True, rotate_shifts=True):
    """
    Generate PtechStaffEntry records (staff×day matrix) for a PTech roster.

    morning_staff  – staff starting on M shift for week 1
    afternoon_staff – staff starting on A shift for week 1
    cm_staff       – ordered list of staff who rotate CM duty on weekends
    post_cm_rest   – give Mon+Tue off after each CM weekend
    rotate_shifts  – alternate M/A each week; if False, shift is fixed for month
    """
    PtechStaffEntry.objects.filter(roster=roster).delete()

    year, month = roster.year, roster.month
    _, num_days = calendar.monthrange(year, month)
    first_day = date(year, month, 1)

    morning_ids = {s.id for s in morning_staff}
    afternoon_ids = {s.id for s in afternoon_staff}
    known_ids = morning_ids | afternoon_ids
    # CM-only staff (not in M/A pools) still need daily entries
    extra_cm = [s for s in cm_staff if s.id not in known_ids]
    all_staff = list(morning_staff) + list(afternoon_staff) + extra_cm
    if not all_staff:
        return

    initial_shift = {s.id: 'M' for s in morning_staff}
    initial_shift.update({s.id: 'A' for s in afternoon_staff})

    unavailability = _build_unavailability_map([s.id for s in all_staff], year, month)

    # First Monday on or after month start (week-rotation anchor)
    fdw = first_day.weekday()
    first_monday = first_day if fdw == 0 else first_day + timedelta(days=(7 - fdw) % 7)

    # Collect SAT-SUN pairs within the month
    weekends = []
    for d in range(1, num_days + 1):
        cur = date(year, month, d)
        if cur.weekday() == 5:  # Saturday
            next_d = date(year, month, d + 1) if d + 1 <= num_days else None
            sun = next_d if (next_d and next_d.weekday() == 6) else None
            weekends.append((cur, sun))

    # Assign CM staff round-robin to each weekend
    cm_pool = list(cm_staff)
    cm_date_staff = {}  # date → staff obj
    for idx, (sat, sun) in enumerate(weekends):
        if not cm_pool:
            break
        cm = cm_pool[idx % len(cm_pool)]
        cm_date_staff[sat] = cm
        if sun:
            cm_date_staff[sun] = cm

    # Build post-CM rest dates: Mon + Tue after each CM weekend
    post_cm_map = {}  # staff_id → set of dates
    if post_cm_rest and cm_pool:
        for idx, (sat, sun) in enumerate(weekends):
            cm = cm_pool[idx % len(cm_pool)]
            base = sun or sat
            for offset in (1, 2):
                rest = base + timedelta(days=offset)
                if rest.month == month:
                    post_cm_map.setdefault(cm.id, set()).add(rest)

    entries = []
    for d in range(1, num_days + 1):
        cur = date(year, month, d)
        unavail = unavailability.get(cur, set())
        is_weekend = cur.weekday() >= 5

        # Week index: 0 = partial days before first Monday, 1 = first full week, …
        if cur < first_monday:
            week_idx = 0
        else:
            week_idx = 1 + (cur - first_monday).days // 7

        for staff in all_staff:
            if is_weekend:
                cm_this = cm_date_staff.get(cur)
                shift = 'CM' if (cm_this and cm_this.id == staff.id) else 'O'
            elif staff.id in unavail:
                shift = 'L'
            elif staff.id in post_cm_map and cur in post_cm_map[staff.id]:
                shift = 'O'
            else:
                base = initial_shift.get(staff.id, 'M')
                if rotate_shifts:
                    # Treat partial week same as week 1; alternate from week 1 onwards
                    eff = max(week_idx, 1)
                    shift = base if (eff - 1) % 2 == 0 else ('A' if base == 'M' else 'M')
                else:
                    shift = base

            entries.append(PtechStaffEntry(roster=roster, staff=staff, date=cur, shift=shift))

    PtechStaffEntry.objects.bulk_create(entries)


def export_ptech_to_excel(roster):
    """Return BytesIO of xlsx matching the FTH Katsina PTech matrix format."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{roster.get_month_display()} {roster.year}"

    unit = roster.unit
    dept = unit.department
    year, month_num = roster.year, roster.month
    _, num_days = calendar.monthrange(year, month_num)
    all_dates = [date(year, month_num, d) for d in range(1, num_days + 1)]

    # Fetch all entries
    entries = roster.ptech_entries.select_related('staff').order_by('staff__name', 'date')
    # Build matrix: staff_id → {date: shift}
    staff_objs = {}  # staff_id → Staff (ordered by name via queryset)
    matrix = {}
    for e in entries:
        staff_objs[e.staff_id] = e.staff
        matrix.setdefault(e.staff_id, {})[e.date] = e.shift

    staff_list = list(staff_objs.values())

    # Styles
    thin = Side(style='thin')
    medium = Side(style='medium')
    border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
    border_med = Border(left=medium, right=medium, top=medium, bottom=medium)

    header_fill = PatternFill('solid', fgColor='1B4F72')
    sub_fill = PatternFill('solid', fgColor='154360')
    date_hdr_fill = PatternFill('solid', fgColor='2E86C1')
    weekend_fill = PatternFill('solid', fgColor='FEF9E7')
    m_fill = PatternFill('solid', fgColor='D6EAF8')
    a_fill = PatternFill('solid', fgColor='D5F5E3')
    cm_fill = PatternFill('solid', fgColor='FDEBD0')
    l_fill = PatternFill('solid', fgColor='FADBD8')
    o_fill = PatternFill('solid', fgColor='F2F3F4')

    shift_fills = {'M': m_fill, 'A': a_fill, 'CM': cm_fill, 'L': l_fill, 'O': o_fill}

    # Split into two halves (days 1-16 and 17-end) like the reference
    halves = [all_dates[:16], all_dates[16:]]

    # Header rows (spanning full width: name col + up to 16 day cols + 1 spacer = 18 cols)
    max_cols = 18

    def merge_header(row, val, fill, font_size=12, bold=True, color='FFFFFF'):
        end_col = get_column_letter(max_cols)
        ws.merge_cells(f'A{row}:{end_col}{row}')
        cell = ws[f'A{row}']
        cell.value = val
        cell.font = Font(name='Calibri', bold=bold, size=font_size, color=color)
        cell.fill = fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border_med
        ws.row_dimensions[row].height = 22

    merge_header(1, dept.hospital.name.upper(), header_fill, font_size=14)
    merge_header(2, dept.department_name.upper(), header_fill, font_size=12)
    merge_header(3, unit.unit_name.upper(), header_fill, font_size=11)
    merge_header(4, roster.roster_title.upper(), sub_fill, font_size=13)
    merge_header(5, roster.month_year_display, PatternFill('solid', fgColor='1A5276'), font_size=12)

    # Name column width
    ws.column_dimensions['A'].width = 26
    for col_idx in range(2, max_cols + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 5

    start_row = 6
    for half_dates in halves:
        if not half_dates:
            continue

        date_row = start_row
        day_row = start_row + 1
        data_start = start_row + 2

        # DATE header row
        ws.row_dimensions[date_row].height = 16
        cell = ws.cell(row=date_row, column=1, value='')
        cell.fill = date_hdr_fill
        cell.border = border_all
        cell = ws.cell(row=date_row, column=2, value='DATE')
        cell.font = Font(name='Calibri', bold=True, size=9, color='FFFFFF')
        cell.fill = date_hdr_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border_all
        for ci, d in enumerate(half_dates, start=3):
            cell = ws.cell(row=date_row, column=ci, value=d.day)
            cell.font = Font(name='Calibri', bold=True, size=9, color='FFFFFF')
            cell.fill = date_hdr_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_all

        # DAY header row
        ws.row_dimensions[day_row].height = 16
        cell = ws.cell(row=day_row, column=1, value='')
        cell.fill = date_hdr_fill
        cell.border = border_all
        cell = ws.cell(row=day_row, column=2, value='DAY')
        cell.font = Font(name='Calibri', bold=True, size=9, color='FFFFFF')
        cell.fill = date_hdr_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border_all
        for ci, d in enumerate(half_dates, start=3):
            is_wknd = d.weekday() >= 5
            cell = ws.cell(row=day_row, column=ci, value=d.strftime('%a').upper())
            cell.font = Font(name='Calibri', bold=True, size=9,
                             color='C0392B' if is_wknd else 'FFFFFF')
            cell.fill = date_hdr_fill if not is_wknd else weekend_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_all

        # Staff rows
        for ri, staff in enumerate(staff_list):
            row = data_start + ri
            ws.row_dimensions[row].height = 17
            cell = ws.cell(row=row, column=1, value=staff.display_name)
            cell.font = Font(name='Calibri', bold=True, size=9, color='1B2631')
            cell.alignment = Alignment(horizontal='left', vertical='center')
            cell.border = border_all

            cell = ws.cell(row=row, column=2, value='')
            cell.border = border_all

            for ci, d in enumerate(half_dates, start=3):
                shift = matrix.get(staff.id, {}).get(d, '')
                is_wknd = d.weekday() >= 5
                fill = shift_fills.get(shift, weekend_fill if is_wknd else PatternFill())
                cell = ws.cell(row=row, column=ci, value=shift)
                cell.font = Font(name='Calibri', bold=(shift == 'CM'), size=9,
                                 color='7D6608' if is_wknd else '1B2631')
                cell.fill = fill
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.border = border_all

        start_row = data_start + len(staff_list) + 1  # blank row between halves

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def export_roster_to_excel(roster):
    """Return BytesIO of xlsx matching the FTH Katsina roster format."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{roster.get_month_display()} {roster.year}"

    unit = roster.unit
    dept = unit.department
    num_slots = roster.num_slots

    # Column widths
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 28
    ws.column_dimensions['D'].width = 4
    ws.column_dimensions['E'].width = 28
    ws.column_dimensions['F'].width = 4
    ws.column_dimensions['G'].width = 28

    total_cols = 3 + (num_slots - 1) * 2  # 3 for 1 slot, 5 for 2, 7 for 3
    last_col = get_column_letter(max(total_cols, 3))

    thin = Side(style='thin')
    medium = Side(style='medium')
    border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
    border_medium = Border(left=medium, right=medium, top=medium, bottom=medium)

    header_fill = PatternFill('solid', fgColor='1B4F72')
    col_fill = PatternFill('solid', fgColor='2E86C1')
    alt_fill = PatternFill('solid', fgColor='EBF5FB')
    weekend_fill = PatternFill('solid', fgColor='FEF9E7')
    white_fill = PatternFill('solid', fgColor='FFFFFF')

    def merge_write(row, val, fill, font_size=12, bold=True, color='FFFFFF'):
        ws.merge_cells(f'A{row}:{last_col}{row}')
        cell = ws[f'A{row}']
        cell.value = val
        cell.font = Font(name='Calibri', bold=bold, size=font_size, color=color)
        cell.fill = fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border_medium
        ws.row_dimensions[row].height = 22

    # ── Header rows ──────────────────────────────────────────────────────────
    merge_write(1, dept.hospital.name.upper(), header_fill, font_size=14)
    merge_write(2, dept.department_name.upper(), header_fill, font_size=12)
    merge_write(3, unit.unit_name.upper(), header_fill, font_size=11)
    merge_write(4, roster.roster_title.upper(), PatternFill('solid', fgColor='154360'), font_size=13)
    merge_write(5, roster.month_year_display, PatternFill('solid', fgColor='1A5276'), font_size=12)

    # ── Column headers ────────────────────────────────────────────────────────
    ws.row_dimensions[6].height = 20
    col_headers = ['DAYS', 'DATE', roster.slot1_label]
    if num_slots >= 2:
        col_headers += ['', roster.slot2_label]
    if num_slots >= 3:
        col_headers += ['', roster.slot3_label]

    for col_idx, hdr in enumerate(col_headers, start=1):
        cell = ws.cell(row=6, column=col_idx, value=hdr)
        cell.font = Font(name='Calibri', bold=True, size=10, color='FFFFFF')
        cell.fill = col_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border_all

    # ── Data rows ─────────────────────────────────────────────────────────────
    entries = roster.entries.select_related('slot1', 'slot2', 'slot3').order_by('date')

    for row_idx, entry in enumerate(entries, start=7):
        ws.row_dimensions[row_idx].height = 18
        is_weekend = entry.date.weekday() in (5, 6)
        row_fill = weekend_fill if is_weekend else (alt_fill if row_idx % 2 == 0 else white_fill)

        data = [
            entry.day_abbr,
            entry.date_display,
            entry.slot1.display_name if entry.slot1 else '',
        ]
        if num_slots >= 2:
            data += ['', entry.slot2.display_name if entry.slot2 else '']
        if num_slots >= 3:
            data += ['', entry.slot3.display_name if entry.slot3 else '']

        for col_idx, val in enumerate(data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.fill = row_fill
            cell.border = border_all
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.font = Font(name='Calibri', size=10,
                             bold=(col_idx == 1),
                             color='7D6608' if is_weekend else '1B2631')

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
