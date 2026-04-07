# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ominicontacto_app', '0117_add_sip_remote_agente_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='agenteprofile',
            name='voicebot',
            field=models.BooleanField(default=False, verbose_name='Voicebot'),
        ),
    ]

