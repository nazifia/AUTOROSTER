from django import forms
from .models import User


class RegistrationForm(forms.Form):
    phone_number = forms.CharField(max_length=20, label='Phone Number')
    full_name = forms.CharField(max_length=200, required=False, label='Full Name')
    password1 = forms.CharField(widget=forms.PasswordInput, label='Password', min_length=8)
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm Password')

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()
        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError('An account with this phone number already exists.')
        return phone

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned

    def save(self):
        return User.objects.create_user(
            phone_number=self.cleaned_data['phone_number'],
            password=self.cleaned_data['password1'],
            full_name=self.cleaned_data.get('full_name', ''),
        )
