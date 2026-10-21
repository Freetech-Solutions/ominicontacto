# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ominicontacto_app', '0122_campana_barajar_contactos'),
    ]

    operations = [
        migrations.AddField(
            model_name='agenteprofile',
            name='voicebot_transport',
            field=models.CharField(
                choices=[('sip', 'SIP'), ('audiosocket', 'AudioSocket')],
                default='sip',
                max_length=16,
                verbose_name='Transporte voicebot',
            ),
        ),
    ]
