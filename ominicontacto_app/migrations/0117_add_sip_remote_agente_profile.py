# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ominicontacto_app', '0116_queue_transcription_resume_percentage'),
    ]

    operations = [
        migrations.AddField(
            model_name='agenteprofile',
            name='sip_remote',
            field=models.BooleanField(default=False, verbose_name='SIP remote'),
        ),
    ]

