from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('roster', '0007_ptech_staff_entry'),
    ]

    operations = [
        migrations.AddField(
            model_name='staff',
            name='staff_type',
            field=models.CharField(
                choices=[('PHARM', 'Pharmacist'), ('PTECH', 'Pharmacy Technician')],
                default='PHARM',
                db_index=True,
                max_length=10,
            ),
        ),
        migrations.AddIndex(
            model_name='staff',
            index=models.Index(
                fields=['unit', 'staff_type', 'is_active'],
                name='roster_staf_unit_stype_idx',
            ),
        ),
    ]
