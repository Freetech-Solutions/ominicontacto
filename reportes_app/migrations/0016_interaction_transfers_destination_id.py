from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reportes_app', '0015_merge_0013_interaction_transfers_destination_fields_0012_speechanalysis'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE public.interaction_transfers
                    RENAME COLUMN destination_target TO destination_id;

                UPDATE public.interaction_transfers
                SET destination_id = substring(destination_id from '(?i)^(agent|campaign)-(.+)$')
                WHERE destination_type IN ('AGENT', 'CAMPAIGN')
                  AND destination_id ~* '^(agent|campaign)-';
            """,
            reverse_sql="""
                ALTER TABLE public.interaction_transfers
                    RENAME COLUMN destination_id TO destination_target;
            """,
        ),
    ]
