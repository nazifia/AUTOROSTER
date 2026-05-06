"""
Run: python seed_data.py
Seeds FTH Katsina pharmacy department, unit, and staff from the sample roster.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autoroster.settings')
django.setup()

from roster.models import Hospital, Department, Unit, Staff

hospital, _ = Hospital.objects.get_or_create(
    name='FEDERAL TEACHING HOSPITAL KATSINA',
    defaults={'address': 'Hospital Road, Katsina'},
)
print(f'Hospital: {hospital}')

dept, _ = Department.objects.get_or_create(
    hospital=hospital,
    department_name='PHARMACY DEPARTMENT',
)
print(f'Department: {dept}')

unit, _ = Unit.objects.get_or_create(
    department=dept,
    unit_name='ACCIDENT AND EMERGENCY PHARMACY UNIT',
)
print(f'Unit: {unit}')

staff_names = [
    'YUSUF BATURE',
    'ZAINAB USMAN',
    'AUWAL KHAMIS',
    'NAZIFI AHMED',
    'IBRAHIM BOYI',
    'FADILA LAWAL',
    'IBRAHIM ABUKUR',
    'HAFSAT DANMUSA',
    'HAFSAT SAULAWA',
]

for name in staff_names:
    s, created = Staff.objects.get_or_create(unit=unit, name=name, defaults={'title': 'PHARM.'})
    print(f'  {"+" if created else "="} {s.display_name}')

print('\nDone! Visit http://127.0.0.1:8000 to start.')
