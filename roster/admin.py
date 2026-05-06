from django.contrib import admin
from .models import Department, Hospital, Staff, StaffAvailability, Roster, RosterEntry, Unit


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ['name', 'address']
    search_fields = ['name']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['hospital', 'department_name', 'unit_count']
    list_filter = ['hospital']

    def unit_count(self, obj):
        return obj.units.count()
    unit_count.short_description = 'Units'


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['unit_name', 'department', 'staff_count']
    list_filter = ['department__hospital', 'department']
    search_fields = ['unit_name']

    def staff_count(self, obj):
        return obj.staff.count()
    staff_count.short_description = 'Staff'


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'unit', 'is_active']
    list_filter = ['unit__department', 'is_active']
    search_fields = ['name']


@admin.register(StaffAvailability)
class StaffAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['staff', 'start_date', 'end_date', 'reason']
    list_filter = ['staff__unit__department', 'staff']
    search_fields = ['staff__name', 'reason']
    date_hierarchy = 'start_date'


class RosterEntryInline(admin.TabularInline):
    model = RosterEntry
    extra = 0


@admin.register(Roster)
class RosterAdmin(admin.ModelAdmin):
    list_display = ['roster_title', 'unit', 'month', 'year', 'num_slots']
    list_filter = ['unit__department', 'year']
    inlines = [RosterEntryInline]


@admin.register(RosterEntry)
class RosterEntryAdmin(admin.ModelAdmin):
    list_display = ['date', 'roster', 'slot1', 'slot2', 'slot3']
    list_filter = ['roster']
    date_hierarchy = 'date'
