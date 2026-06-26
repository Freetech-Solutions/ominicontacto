from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('ominicontacto_app', '0118_auto_20260506_1259'),
        ('email_app', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConversacionEmail',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('thread_key', models.CharField(db_index=True, max_length=254)),
                ('subject', models.CharField(blank=True, default='', max_length=254)),
                ('client_mail', models.CharField(blank=True, default='', max_length=254)),
                ('client_name', models.CharField(blank=True, default='', max_length=100)),
                ('is_active', models.BooleanField(default=True)),
                ('atendida', models.BooleanField(default=False)),
                ('is_disposition', models.BooleanField(default=False)),
                ('status', models.CharField(
                    choices=[
                        ('new', 'new'),
                        ('assigned', 'assigned'),
                        ('in_progress', 'in_progress'),
                        ('answered', 'answered'),
                        ('reopened', 'reopened'),
                        ('closed', 'closed'),
                    ],
                    db_index=True,
                    default='new',
                    max_length=20,
                )),
                ('timestamp', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('date_last_interaction', models.DateTimeField(null=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='conversations', to='email_app.account')),
                ('agent', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='email_conversations', to='ominicontacto_app.agenteprofile')),
                ('campana', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='email_conversations', to='ominicontacto_app.campana')),
                ('contacto', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='email_conversations', to='ominicontacto_app.contacto')),
                ('conversation_disposition', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ominicontacto_app.historicalcalificacioncliente')),
            ],
            options={
                'ordering': ['-date_last_interaction', '-id'],
            },
        ),
        migrations.AddField(
            model_name='message',
            name='conversation',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mensajes', to='email_app.conversacionemail'),
        ),
        migrations.AddField(
            model_name='message',
            name='direction',
            field=models.CharField(choices=[('inbound', 'inbound'), ('outbound', 'outbound')], default='inbound', max_length=10),
        ),
        migrations.AddField(
            model_name='message',
            name='is_read',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='message',
            name='status',
            field=models.CharField(default='received', max_length=20),
        ),
        migrations.AddField(
            model_name='message',
            name='fail_reason',
            field=models.CharField(blank=True, default='', max_length=254),
        ),
        migrations.AddField(
            model_name='message',
            name='sender',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='message',
            name='type',
            field=models.CharField(default='email', max_length=20),
        ),
    ]
