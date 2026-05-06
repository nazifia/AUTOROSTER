from django import forms
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, HTML, Div, Field
from .models import Department, Hospital, Staff, Roster, Unit, StaffAvailability

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
        fields = ['unit', 'title', 'name', 'is_active']
        widgets = {
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. PHARM.'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. IBRAHIM ABUKUR'}),
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
                Column('unit', css_class='col-md-6'),
                Column('title', css_class='col-md-2'),
                Column('name', css_class='col-md-4'),
            ),
            Field('is_active'),
            Submit('submit', 'Save Staff', css_class='btn btn-primary mt-3'),
        )


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
        queryset=Staff.objects.filter(is_active=True).select_related('unit__department'),
        widget=forms.CheckboxSelectMultiple(),
        label='Slot 1 Staff Pool (rotates in order)',
    )
    slot1_mode = forms.ChoiceField(
        choices=[('rotate', 'Rotate (round-robin)'), ('fixed', 'Fixed (always first selected)')],
        widget=forms.RadioSelect(),
        initial='rotate',
        label='Slot 1 Mode',
    )
    slot2_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True).select_related('unit__department'),
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
    slot3_staff = forms.ModelMultipleChoiceField(
        queryset=Staff.objects.filter(is_active=True).select_related('unit__department'),
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

    def clean(self):
        cleaned = super().clean()
        num_slots = int(cleaned.get('num_slots', 3))
        if not cleaned.get('slot1_staff'):
            raise ValidationError('Select at least one staff for Slot 1.')
        if num_slots >= 2 and not cleaned.get('slot2_staff'):
            raise ValidationError('Select at least one staff for Slot 2.')
        if num_slots >= 3 and not cleaned.get('slot3_staff'):
            raise ValidationError('Select at least one staff for Slot 3.')
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
        queryset=Staff.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    slot2 = forms.ModelChoiceField(
        queryset=Staff.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    slot3 = forms.ModelChoiceField(
        queryset=Staff.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
