from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse

from roster.views import can_view_log, error, form_errors, is_admin
from .forms import RegistrationForm


def me_json(user):
    return {'id': user.pk, 'name': str(user), 'phone_number': user.phone_number,
            'is_admin': is_admin(user), 'can_view_log': can_view_log(user)}


def register_view(request):
    if request.method != 'POST':
        return error('POST only', 405)
    form = RegistrationForm(request.POST)
    if not form.is_valid():
        return form_errors(form)
    user = form.save()
    login(request, user)
    return JsonResponse(me_json(user), status=201)


def login_view(request):
    if request.method != 'POST':
        return error('POST only', 405)
    user = authenticate(request, phone_number=request.POST.get('phone_number', '').strip(),
                        password=request.POST.get('password', ''))
    if not user:
        return error('Invalid phone number or password.', 400)
    login(request, user)
    return JsonResponse(me_json(user))


def logout_view(request):
    if request.method != 'POST':
        return error('POST only', 405)
    logout(request)
    return JsonResponse({'ok': True})


def me_view(request):
    if not request.user.is_authenticated:
        return error('Authentication required.', 401)
    return JsonResponse(me_json(request.user))
