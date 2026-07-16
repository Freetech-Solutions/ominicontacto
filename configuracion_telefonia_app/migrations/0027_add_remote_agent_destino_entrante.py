# Generated migration to add REMOTE_AGENT destination type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion_telefonia_app', '0026_instagram_destinoentrante_tipo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='destinoentrante',
            name='tipo',
            field=models.PositiveIntegerField(choices=[
                (1, 'Campaña entrante'),
                (2, 'Validación de fecha/hora'),
                (3, 'IVR'),
                (5, 'HangUp'),
                (9, 'Identificador cliente'),
                (7, 'Destino personalizado'),
                (10, 'Menú Interactivo de Whatsapp'),
                (11, 'Agente'),
                (6, 'CX Survey'),
                (12, 'Mensaje de Cierre'),
                (13, 'Menú Interactivo de Messenger Meta App'),
                (14, 'Menú Interactivo de Instagram'),
                (15, 'Agente Remoto'),
            ]),
        ),
    ]

