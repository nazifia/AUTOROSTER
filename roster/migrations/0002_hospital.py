import django.db.models.deletion
from django.db import migrations, models


def migrate_hospital_data(apps, schema_editor):
    Department = apps.get_model('roster', 'Department')
    Hospital = apps.get_model('roster', 'Hospital')
    for dept in Department.objects.all():
        hospital, _ = Hospital.objects.get_or_create(name=dept.hospital_name)
        dept.hospital = hospital
        dept.save()


class Migration(migrations.Migration):

    dependencies = [
        ('roster', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Hospital',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
                ('address', models.CharField(blank=True, max_length=300)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='department',
            name='hospital',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='departments',
                to='roster.hospital',
            ),
        ),
        migrations.RunPython(migrate_hospital_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='department',
            name='hospital',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='departments',
                to='roster.hospital',
            ),
        ),
        migrations.RemoveField(
            model_name='department',
            name='hospital_name',
        ),
        migrations.AlterModelOptions(
            name='department',
            options={'ordering': ['hospital__name', 'department_name']},
        ),
    ]
