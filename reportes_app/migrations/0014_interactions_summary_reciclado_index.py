from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reportes_app', '0013_interaction_transfers_destination_fields'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS idx_summ_reciclado_campaign_customer_start
                ON public.interactions_summary (campaign_id, customer_id, start_time DESC)
                WHERE channel_type = 'VOICE'
                  AND direction = 'OUTBOUND'
                  AND customer_id IS NOT NULL;
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS public.idx_summ_reciclado_campaign_customer_start;
            """,
        ),
    ]
