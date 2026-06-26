from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ominicontacto_app', '0118_auto_20260506_1259'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calificacioncliente',
            name='canalidad',
            field=models.PositiveIntegerField(choices=[(0, 'Teléfono'), (1, 'Whatsapp'), (2, 'Facebook'), (3, 'Instagram'), (4, 'Email')], default=0),
        ),
        migrations.AlterField(
            model_name='historicalcalificacioncliente',
            name='canalidad',
            field=models.PositiveIntegerField(choices=[(0, 'Teléfono'), (1, 'Whatsapp'), (2, 'Facebook'), (3, 'Instagram'), (4, 'Email')], default=0),
        ),
    ]
