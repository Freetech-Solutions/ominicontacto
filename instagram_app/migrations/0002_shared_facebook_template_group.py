from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facebook_meta_app', '0001_initial'),
        ('instagram_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracioninstagramcampana',
            name='grupo_plantilla_facebook',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='configuracion_instagram',
                to='facebook_meta_app.grupoplantillamessenger',
            ),
        ),
    ]
