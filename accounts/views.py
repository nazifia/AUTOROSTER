from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render

from .forms import RegistrationForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        phone = request.POST.get('phone_number', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, phone_number=phone, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get('next', 'dashboard'))
        error = 'Invalid phone number or password.'
    return render(request, 'accounts/login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('login')
