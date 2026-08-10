# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ominicontacto_app', '0121_add_sip_remote_agente_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='campana',
            name='barajar_contactos',
            field=models.BooleanField(default=False),
        ),
    ]
