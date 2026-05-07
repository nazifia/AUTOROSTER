from django import forms
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, HTML, Div, Field
from .models import (Department, Hospital, Staff, Roster, Unit, StaffAvailability,
                      ROSTER_TYPE_CHOICES, PTECH_SHIFT_CONFIG_CHOICES, SHIFT_CONFIG_DETAILS,
                      STAFF_TYPE_CHOICES)

CURRENT_YEAR = 2026


class HospitalForm(forms.ModelForm):
    class Meta:
        model = Hospital
        fields = ['name', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. FEDERAL TEACHING HOSPITAL KATSINA'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Hospital Road, Katsina'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'name',
            'address',
            Submit('submit', 'Save Hospital', css_class='btn btn-primary mt-3'),
        )


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['hospital', 'department_name']
        widgets = {
            'hospital': forms.Select(attrs={'class': 'form-select'}),
            'department_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. PHARMACY DEPARTMENT'}),
        }

    def __init__(self, *args, **kwargs):
        hospital_id = kwargs.pop('hospital_id', None)
        super().__init__(*args, **kwargs)
        if hospital_id:
            self.fields['hospital'].initial = hospital_id
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'hospital',
            'department_name',
            Submit('submit', 'Save Department', css_class='btn btn-primary mt-3'),
        )


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['department', 'unit_name']
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'unit_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ACCIDENT AND EMERGENCY PHARMACY UNIT'}),
        }

    def __init__(self, *args, **kwargs):
        department_id = kwargs.pop('department_id', None)
        super().__init__(*args, **kwargs)
        if department_id:
            self.fields['department'].initial = department_id
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'department',
            'unit_name',
            Submit('submit', 'Save Unit', css_class='btn btn-primary mt-3'),
        )


class StaffForm(forms.ModelForm):
    class Meta:
        model = Staff
        fields = ['unit', 'staff_type', 'title', 'name', 'phone_number', 'is_active']
        widgets = {
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'staff_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. PHARM.'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. IBRAHIM ABUKUR'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 08012345678'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        unit_id = kwargs.pop('unit_id', None)
        kwargs.pop('department_id', None)  # backwards compat
        super().__init__(*args, **kwargs)
        if unit_id:
            self.fields['unit'].initial = unit_id
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('unit', css_class='col-md-4'),
                Column('staff_type', css_class='col-md-3'),
                Column('title', css_class='col-md-2'),
                Column('name', css_class='col-md-3'),
            ),
            Row(
                Column('phone_number', css_class='col-md-4'),
            ),
            Field('is_active'),
            Submit('submit', 'Save Staff', css_class='btn btn-primary mt-3'),
        )


DAYS_OF_WEEK_CHOICES = [
    ('0', 'Mon'), ('1', 'Tue'), ('2', 'Wed'), ('3', 'Thu'),
    ('4', 'Fri'), ('5', 'Sat'), ('6', 'Sun'),
]

DAYS_PATTERN_CHOICES = [
    ('all', 'Every day'),
    ('weekdays', 'Weekdays only (Mon–Fri)'),
    ('weekends', 'Weekends only (Sat–Sun)'),
    ('custom', 'Custom days'),
]


class RosterGenerateForm(forms.Form):
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.select_related('department__hospital').all(),
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_unit'}),
        label='Unit',
    )
    roster_title = forms.CharField(
        initial="PHARMACISTS' CALL DUTY ROSTER",
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    roster_type = forms.ChoiceField(
        choices=ROSTER_TYPE_CHOICES,
        initial='CALL',
        widget=forms.RadioSelect(attrs={'id': 'id_roster_type'}),
        label='Roster Type',
    )
    shift_config = forms.ChoiceField(
        choices=PTECH_SHIFT_CONFIG_CHOICES,
        required=False,
        widget=forms.RadioSelect(attrs={'id': 'id_shift_config', 'class': 'ptech-only'}),
        label='PTech Shift Configuration',
    )
    month = forms.ChoiceField(
        choices=[(i, f"{i:02d} — {__import__('calendar').month_name[i]}") for i in range(1, 13)],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    year = forms.IntegerField(
        initial=CURRENT_YEAR,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 2020, 'max': 2100}),
    )
    num_slots = forms.ChoiceField(
        choices=[(1, '1 Slot'), (2, '2 Slots'), (3, '3 Slots')],
        initial=3,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_num_slots'}),
        label='Number of Call Slots',
    )
    slot1_label = forms.CharField(
        initial='FIRST ON CALL',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Slot 1 Label',
    )
    slot2_label = forms.CharField(
        initial='SECOND ON CALL',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Slot 2 Label',
    )
    slot3_label = forms.CharField(
        initial='THIRD ON CALL',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Slot 3 Label',
    )
    slot1_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Slot 1 Staff Pool (rotates in order)',
    )
    slot1_mode = forms.ChoiceField(
        choices=[('rotate', 'Rotate (round-robin)'), ('fixed', 'Fixed (always first selected)')],
        widget=forms.RadioSelect(),
        initial='rotate',
        label='Slot 1 Mode',
    )
    slot1_days_pattern = forms.ChoiceField(
        choices=DAYS_PATTERN_CHOICES,
        initial='all',
        widget=forms.RadioSelect(attrs={'class': 'days-pattern-radio'}),
        label='Apply on',
    )
    slot1_custom_days = forms.MultipleChoiceField(
        choices=DAYS_OF_WEEK_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label='Custom days',
    )
    slot1_min_gap = forms.IntegerField(
        initial=0, min_value=0, max_value=6, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:80px'}),
        label='Min days between same staff (0 = no restriction)',
    )

    slot2_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Slot 2 Staff Pool',
    )
    slot2_mode = forms.ChoiceField(
        choices=[('rotate', 'Rotate (round-robin)'), ('fixed', 'Fixed (always first selected)')],
        widget=forms.RadioSelect(),
        initial='fixed',
        label='Slot 2 Mode',
    )
    slot2_days_pattern = forms.ChoiceField(
        choices=DAYS_PATTERN_CHOICES,
        initial='all',
        widget=forms.RadioSelect(attrs={'class': 'days-pattern-radio'}),
        label='Apply on',
    )
    slot2_custom_days = forms.MultipleChoiceField(
        choices=DAYS_OF_WEEK_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label='Custom days',
    )
    slot2_min_gap = forms.IntegerField(
        initial=0, min_value=0, max_value=6, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:80px'}),
        label='Min days between same staff (0 = no restriction)',
    )

    slot3_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Slot 3 Staff Pool',
    )
    slot3_mode = forms.ChoiceField(
        choices=[('rotate', 'Rotate (round-robin)'), ('fixed', 'Fixed (always first selected)')],
        widget=forms.RadioSelect(),
        initial='fixed',
        label='Slot 3 Mode',
    )
    slot3_days_pattern = forms.ChoiceField(
        choices=DAYS_PATTERN_CHOICES,
        initial='all',
        widget=forms.RadioSelect(attrs={'class': 'days-pattern-radio'}),
        label='Apply on',
    )
    slot3_custom_days = forms.MultipleChoiceField(
        choices=DAYS_OF_WEEK_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label='Custom days',
    )
    slot3_min_gap = forms.IntegerField(
        initial=0, min_value=0, max_value=6, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:80px'}),
        label='Min days between same staff (0 = no restriction)',
    )

    # ── PTech shift fields ────────────────────────────────────────────────────
    ptech_morning_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PTECH').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Morning (M) Staff — start on Morning shift',
    )
    ptech_afternoon_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PTECH').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Afternoon (A) Staff — start on Afternoon shift',
    )
    ptech_cm_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PTECH').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Night (N) Weekend Rotation Staff (rotates in alphabetical order)',
    )
    ptech_rotate_shifts = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Rotate shifts weekly (M↔A each week)',
    )
    ptech_post_cm_rest = forms.IntegerField(
        required=False,
        initial=2,
        min_value=0,
        max_value=7,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '0', 'max': '7'}),
        label='Rest days after Night duty (0 = none, 2–7)',
    )
    ptech_cm_min_gap = forms.IntegerField(
        initial=0, min_value=0, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:80px'}),
        label='Min days between Night assignments for same staff (0 = no restriction)',
    )

    ptech_active_shifts = forms.MultipleChoiceField(
        choices=[('M', 'Morning (M)'), ('A', 'Afternoon (A)'), ('N', 'Night (N)')],
        initial=['M', 'A', 'N'],
        widget=forms.CheckboxSelectMultiple(),
        required=True,
        label='Shifts to include in roster',
    )

    ptech_morning_work_days = forms.IntegerField(
        initial=5, min_value=1, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '1', 'max': '30'}),
        label='Morning: work days',
    )
    ptech_morning_off_days = forms.IntegerField(
        initial=2, min_value=0, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '0', 'max': '30'}),
        label='Morning: off days',
    )
    ptech_afternoon_work_days = forms.IntegerField(
        initial=5, min_value=1, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '1', 'max': '30'}),
        label='Afternoon: work days',
    )
    ptech_afternoon_off_days = forms.IntegerField(
        initial=2, min_value=0, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '0', 'max': '30'}),
        label='Afternoon: off days',
    )
    ptech_night_work_days = forms.IntegerField(
        initial=2, min_value=1, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '1', 'max': '30'}),
        label='Night: work days',
    )
    ptech_night_off_days = forms.IntegerField(
        initial=5, min_value=0, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '0', 'max': '30'}),
        label='Night: off days',
    )

    # ── Pharmacist shift fields ───────────────────────────────────────────────
    pharm_morning_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Morning (M) Staff — start on Morning shift',
    )
    pharm_afternoon_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Afternoon (A) Staff — start on Afternoon shift',
    )
    pharm_night_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM').select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Night (N) Staff — start on Night shift',
    )
    pharm_rotate_shifts = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Rotate shifts (M↔A↔N cycle)',
    )
    pharm_active_shifts = forms.MultipleChoiceField(
        choices=[('M', 'Morning (M)'), ('A', 'Afternoon (A)'), ('N', 'Night (N)')],
        initial=['M', 'A', 'N'],
        widget=forms.CheckboxSelectMultiple(),
        required=True,
        label='Shifts to include in roster',
    )
    pharm_morning_work_days = forms.IntegerField(
        initial=5, min_value=1, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '1', 'max': '30'}),
        label='Morning: work days',
    )
    pharm_morning_off_days = forms.IntegerField(
        initial=2, min_value=0, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '0', 'max': '30'}),
        label='Morning: off days',
    )
    pharm_afternoon_work_days = forms.IntegerField(
        initial=5, min_value=1, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '1', 'max': '30'}),
        label='Afternoon: work days',
    )
    pharm_afternoon_off_days = forms.IntegerField(
        initial=2, min_value=0, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '0', 'max': '30'}),
        label='Afternoon: off days',
    )
    pharm_night_work_days = forms.IntegerField(
        initial=2, min_value=1, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '1', 'max': '30'}),
        label='Night: work days',
    )
    pharm_night_off_days = forms.IntegerField(
        initial=5, min_value=0, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:70px', 'min': '0', 'max': '30'}),
        label='Night: off days',
    )
    pharm_night_min_gap = forms.IntegerField(
        initial=0, min_value=0, max_value=30, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'width:80px'}),
        label='Min days between Night assignments for same staff (0 = no restriction)',
    )

    def clean(self):
        cleaned = super().clean()
        roster_type = cleaned.get('roster_type')

        if roster_type == 'PTECH':
            active_shifts = cleaned.get('ptech_active_shifts') or []
            if not active_shifts:
                raise ValidationError('Select at least one shift to include in the roster.')
            morning = cleaned.get('ptech_morning_staff') or []
            afternoon = cleaned.get('ptech_afternoon_staff') or []
            cm = cleaned.get('ptech_cm_staff') or []
            if not morning and not afternoon and not cm:
                raise ValidationError('Select at least one staff for Morning, Afternoon, or Night shift.')
        elif roster_type == 'PHARM_SHIFT':
            active_shifts = cleaned.get('pharm_active_shifts') or []
            if not active_shifts:
                raise ValidationError('Select at least one shift to include in the roster.')
            morning = cleaned.get('pharm_morning_staff') or []
            afternoon = cleaned.get('pharm_afternoon_staff') or []
            night = cleaned.get('pharm_night_staff') or []
            if not morning and not afternoon and not night:
                raise ValidationError('Select at least one staff for Morning, Afternoon, or Night shift.')
        else:
            num_slots = int(cleaned.get('num_slots', 3))
            if not cleaned.get('slot1_staff'):
                raise ValidationError('Select at least one staff for Slot 1.')
            if num_slots >= 2 and not cleaned.get('slot2_staff'):
                raise ValidationError('Select at least one staff for Slot 2.')
            if num_slots >= 3 and not cleaned.get('slot3_staff'):
                raise ValidationError('Select at least one staff for Slot 3.')
            for n in range(1, num_slots + 1):
                if cleaned.get(f'slot{n}_days_pattern') == 'custom' and not cleaned.get(f'slot{n}_custom_days'):
                    raise ValidationError(f'Slot {n}: select at least one custom day.')
        return cleaned


class StaffAvailabilityForm(forms.ModelForm):
    class Meta:
        model = StaffAvailability
        fields = ['start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Annual leave, Training'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            raise ValidationError('End date must be on or after start date.')
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('start_date', css_class='col-md-4'),
                Column('end_date', css_class='col-md-4'),
                Column('reason', css_class='col-md-4'),
            ),
            Submit('submit', 'Save', css_class='btn btn-primary mt-2'),
        )


class RosterEntryEditForm(forms.Form):
    slot1 = forms.ModelChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    slot2 = forms.ModelChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    slot3 = forms.ModelChoiceField(
        queryset=Staff.objects.filter(is_active=True, staff_type='PHARM'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
