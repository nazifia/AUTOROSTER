import calendar
from datetime import date
from io import BytesIO

import openpyxl
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side
)
from openpyxl.utils import get_column_letter

from datetime import timedelta

from .models import RosterEntry, StaffAvailability


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


def _pick(pool, idx, unavailable_ids, mode):
    """Pick next available staff from pool; return (staff_or_None, new_idx)."""
    if not pool:
        return None, idx
    if mode == 'fixed':
        for s in pool:
            if s.id not in unavailable_ids:
                return s, idx
        return None, idx
    # rotate: find next available starting from idx
    for offset in range(len(pool)):
        candidate = pool[(idx + offset) % len(pool)]
        if candidate.id not in unavailable_ids:
            return candidate, (idx + offset + 1) % len(pool)
    return None, idx


def generate_roster_entries(roster, slot1_staff, slot2_staff, slot3_staff,
                            slot1_mode='rotate', slot2_mode='rotate', slot3_mode='rotate'):
    """
    Generate RosterEntry objects for every day in the roster's month/year.
    Respects StaffAvailability records — unavailable staff are skipped per day.
    mode: 'rotate' = round-robin, 'fixed' = always first available in list
    """
    RosterEntry.objects.filter(roster=roster).delete()

    year, month = roster.year, roster.month
    _, num_days = calendar.monthrange(year, month)

    s1_pool = list(slot1_staff)
    s2_pool = list(slot2_staff)
    s3_pool = list(slot3_staff)

    all_staff_ids = {s.id for s in s1_pool + s2_pool + s3_pool}
    unavailability = _build_unavailability_map(all_staff_ids, year, month)

    s1_idx = s2_idx = s3_idx = 0
    entries = []

    for day in range(1, num_days + 1):
        d = date(year, month, day)
        unavail = unavailability.get(d, set())

        s1 = s2 = s3 = None

        if s1_pool:
            s1, s1_idx = _pick(s1_pool, s1_idx, unavail, slot1_mode)

        if s2_pool and roster.num_slots >= 2:
            s2, s2_idx = _pick(s2_pool, s2_idx, unavail, slot2_mode)

        if s3_pool and roster.num_slots >= 3:
            s3, s3_idx = _pick(s3_pool, s3_idx, unavail, slot3_mode)

        entries.append(RosterEntry(roster=roster, date=d, slot1=s1, slot2=s2, slot3=s3))

    RosterEntry.objects.bulk_create(entries)


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
