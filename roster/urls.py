from django.urls import path
from . import views

# Mounted under /api/ — the JSON API the web/ frontend talks to.
urlpatterns = [
    path('lookups/', views.lookups, name='lookups'),
    path('dashboard/', views.dashboard, name='dashboard'),

    path('hospitals/', views.hospital_list, name='hospital_list'),
    path('hospitals/<int:pk>/', views.hospital_detail, name='hospital_detail'),

    path('departments/', views.department_list, name='department_list'),
    path('departments/<int:pk>/', views.department_detail, name='department_detail'),

    path('units/', views.unit_list, name='unit_list'),
    path('units/<int:pk>/', views.unit_detail, name='unit_detail'),

    path('staff/', views.staff_list, name='staff_list'),
    path('staff/<int:pk>/', views.staff_detail, name='staff_detail'),
    path('staff/<int:pk>/availability/', views.staff_availability, name='staff_availability'),
    path('availability/<int:pk>/', views.staff_availability_delete, name='staff_availability_delete'),

    path('rosters/', views.roster_list, name='roster_list'),
    path('rosters/generate/', views.roster_generate, name='roster_generate'),
    path('rosters/<int:pk>/', views.roster_detail, name='roster_detail'),
    path('rosters/<int:pk>/export/', views.roster_export, name='roster_export'),

    path('entries/<int:pk>/', views.entry_update, name='entry_update'),
    path('ptech-entries/<int:pk>/', views.ptech_entry_update, name='ptech_entry_update'),

    path('activity/', views.activity_log, name='activity_log'),
    path('activity/access/', views.manage_activity_log_access, name='manage_activity_log_access'),
]
