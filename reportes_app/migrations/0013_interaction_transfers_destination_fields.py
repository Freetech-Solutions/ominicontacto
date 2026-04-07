from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reportes_app', '0012_new_interactionlogs_agentlogs'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE public.interaction_transfers
                    ADD COLUMN IF NOT EXISTS destination_agent_id INTEGER,
                    ADD COLUMN IF NOT EXISTS destination_campaign_id INTEGER,
                    ADD COLUMN IF NOT EXISTS destination_external_endpoint VARCHAR(128);

                CREATE INDEX IF NOT EXISTS idx_transfers_dest_agent_id
                    ON public.interaction_transfers (destination_agent_id);

                CREATE INDEX IF NOT EXISTS idx_transfers_dest_campaign_id
                    ON public.interaction_transfers (destination_campaign_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS public.idx_transfers_dest_campaign_id;
                DROP INDEX IF EXISTS public.idx_transfers_dest_agent_id;

                ALTER TABLE public.interaction_transfers
                    DROP COLUMN IF EXISTS destination_external_endpoint,
                    DROP COLUMN IF EXISTS destination_campaign_id,
                    DROP COLUMN IF EXISTS destination_agent_id;
            """,
        ),
    ]
