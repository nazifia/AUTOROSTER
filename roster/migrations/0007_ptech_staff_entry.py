from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('roster', '0006_add_ptech_roster_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='PtechStaffEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('shift', models.CharField(
                    choices=[('M', 'Morning'), ('A', 'Afternoon'), ('O', 'Off'),
                             ('CM', 'Combined Morning'), ('L', 'Leave')],
                    max_length=2,
                )),
                ('roster', models.ForeignKey(
                    db_index=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name='ptech_entries', to='roster.roster',
                )),
                ('staff', models.ForeignKey(
                    db_index=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name='ptech_entries', to='roster.staff',
                )),
            ],
            options={
                'ordering': ['date', 'staff__name'],
                'unique_together': {('roster', 'staff', 'date')},
            },
        ),
        migrations.AddIndex(
            model_name='ptechstaffentry',
            index=models.Index(fields=['roster', 'date'], name='roster_ptec_roster__date_idx'),
        ),
        migrations.AddIndex(
            model_name='ptechstaffentry',
            index=models.Index(fields=['roster', 'staff'], name='roster_ptec_roster__staff_idx'),
        ),
    ]
