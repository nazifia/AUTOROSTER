from django.db import migrations, models
import django.db.models.deletion


def create_units_from_departments(apps, schema_editor):
    Department = apps.get_model('roster', 'Department')
    Unit = apps.get_model('roster', 'Unit')
    Staff = apps.get_model('roster', 'Staff')
    Roster = apps.get_model('roster', 'Roster')

    for dept in Department.objects.all():
        unit_name = getattr(dept, 'unit_name', dept.department_name)
        unit = Unit.objects.create(department=dept, unit_name=unit_name)
        Staff.objects.filter(department=dept).update(unit=unit)
        Roster.objects.filter(department=dept).update(unit=unit)


class Migration(migrations.Migration):

    dependencies = [
        ('roster', '0002_hospital'),
    ]

    operations = [
        # Add Unit model
        migrations.CreateModel(
            name='Unit',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('unit_name', models.CharField(max_length=200)),
                ('department', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='units',
                    to='roster.department',
                )),
            ],
            options={'ordering': ['department__department_name', 'unit_name']},
        ),
        # Add nullable unit FK to Staff
        migrations.AddField(
            model_name='staff',
            name='unit',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='staff',
                to='roster.unit',
            ),
        ),
        # Add nullable unit FK to Roster
        migrations.AddField(
            model_name='roster',
            name='unit',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='rosters',
                to='roster.unit',
            ),
        ),
        # Data migration: create units, reassign staff/rosters
        migrations.RunPython(create_units_from_departments, migrations.RunPython.noop),
        # Make Staff.unit non-nullable
        migrations.AlterField(
            model_name='staff',
            name='unit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='staff',
                to='roster.unit',
            ),
        ),
        # Make Roster.unit non-nullable
        migrations.AlterField(
            model_name='roster',
            name='unit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='rosters',
                to='roster.unit',
            ),
        ),
        # Drop old unique_together on Roster
        migrations.AlterUniqueTogether(name='roster', unique_together=set()),
        # Remove old department FK from Staff
        migrations.RemoveField(model_name='staff', name='department'),
        # Remove old department FK from Roster
        migrations.RemoveField(model_name='roster', name='department'),
        # Remove unit_name from Department
        migrations.RemoveField(model_name='department', name='unit_name'),
        # Add new unique_together on Roster
        migrations.AlterUniqueTogether(
            name='roster',
            unique_together={('unit', 'month', 'year')},
        ),
    ]
