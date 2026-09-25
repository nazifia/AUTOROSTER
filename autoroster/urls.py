from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from roster.views import spa

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('roster.urls')),
    path('', spa, name='spa'),
    # ponytail: Django serves the frontend's few static files itself; put them
    # behind whitenoise or the web server if traffic ever makes this matter.
    re_path(r'^(?P<path>[\w-]+\.(?:js|css))$', serve, {'document_root': settings.BASE_DIR / 'web'}),
]
