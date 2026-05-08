from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Hospitals
    path('hospitals/', views.hospital_list, name='hospital_list'),
    path('hospitals/add/', views.hospital_create, name='hospital_create'),
    path('hospitals/<int:pk>/', views.hospital_detail, name='hospital_detail'),
    path('hospitals/<int:pk>/edit/', views.hospital_edit, name='hospital_edit'),
    path('hospitals/<int:pk>/delete/', views.hospital_delete, name='hospital_delete'),

    # Departments
    path('departments/', views.department_list, name='department_list'),
    path('departments/add/', views.department_create, name='department_create'),
    path('departments/<int:pk>/edit/', views.department_edit, name='department_edit'),
    path('departments/<int:pk>/delete/', views.department_delete, name='department_delete'),

    # Units
    path('units/', views.unit_list, name='unit_list'),
    path('units/add/', views.unit_create, name='unit_create'),
    path('units/<int:pk>/edit/', views.unit_edit, name='unit_edit'),
    path('units/<int:pk>/delete/', views.unit_delete, name='unit_delete'),

    # Staff
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', views.staff_create, name='staff_create'),
    path('staff/<int:pk>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<int:pk>/delete/', views.staff_delete, name='staff_delete'),
    path('staff/<int:pk>/availability/', views.staff_availability, name='staff_availability'),
    path('availability/<int:pk>/delete/', views.staff_availability_delete, name='staff_availability_delete'),

    # Rosters
    path('rosters/', views.roster_list, name='roster_list'),
    path('rosters/generate/', views.roster_generate, name='roster_generate'),
    path('rosters/<int:pk>/', views.roster_detail, name='roster_detail'),
    path('rosters/<int:pk>/delete/', views.roster_delete, name='roster_delete'),
    path('rosters/<int:pk>/export/', views.roster_export, name='roster_export'),

    # Entry inline edit (AJAX)
    path('entries/<int:pk>/update/', views.entry_update, name='entry_update'),
    path('ptech-entries/<int:pk>/update/', views.ptech_entry_update, name='ptech_entry_update'),

    # Activity Log
    path('activity/', views.activity_log, name='activity_log'),
    path('activity/access/', views.manage_activity_log_access, name='manage_activity_log_access'),

    # API
    path('api/units/<int:dept_id>/', views.staff_by_department, name='units_by_department'),
    path('api/staff-unit/<int:unit_id>/', views.staff_by_unit, name='staff_by_unit'),
]
