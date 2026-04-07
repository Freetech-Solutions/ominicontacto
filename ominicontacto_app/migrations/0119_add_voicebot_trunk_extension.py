# Generated manually

from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion_telefonia_app', '0001_initial'),
        ('ominicontacto_app', '0118_add_voicebot_agente_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='agenteprofile',
            name='voicebot_trunk',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='agentes_voicebot',
                to='configuracion_telefonia_app.troncalsip',
                verbose_name='Troncal SIP (voicebot)',
            ),
        ),
        migrations.AddField(
            model_name='agenteprofile',
            name='voicebot_extension',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(999999),
                ],
                verbose_name='Extensión voicebot (1-999999)',
            ),
        ),
    ]
