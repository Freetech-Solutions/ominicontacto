from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            'reportes_app',
            '0017_merge_0014_interactions_summary_reciclado_index_0016_interaction_transfers_destination_id',
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE public.interactions_summary
                    DROP CONSTRAINT IF EXISTS interactions_summary_initiation_method_valid;

                ALTER TABLE public.interactions_summary
                    ADD CONSTRAINT interactions_summary_initiation_method_valid
                    CHECK (
                        initiation_method IS NULL
                        OR initiation_method IN ('AGENT', 'DIALER', 'BOT', 'EXTERNAL')
                    );
            """,
            reverse_sql="""
                UPDATE public.interactions_summary
                   SET initiation_method = NULL
                 WHERE initiation_method = 'EXTERNAL';

                ALTER TABLE public.interactions_summary
                    DROP CONSTRAINT IF EXISTS interactions_summary_initiation_method_valid;

                ALTER TABLE public.interactions_summary
                    ADD CONSTRAINT interactions_summary_initiation_method_valid
                    CHECK (
                        initiation_method IS NULL
                        OR initiation_method IN ('AGENT', 'DIALER', 'BOT')
                    );
            """,
        ),
    ]
