# Fix: app_secret was added to 0001_initial after some environments already
# applied that migration. Facebook Meta got a proper 0002; Instagram did not.
# This migration adds the column only if it is missing. The model state already
# includes the field via 0001_initial.

from django.db import migrations


def add_app_secret_if_missing(apps, schema_editor):
    table = 'instagram_app_cuentainstagram'
    column = 'app_secret'
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                """,
                [table, column],
            )
            if cursor.fetchone():
                return
            cursor.execute(
                'ALTER TABLE {} ADD COLUMN {} varchar(255) NULL'.format(table, column)
            )
            return

        # SQLite / other backends used in tests
        existing = [
            field.name for field in connection.introspection.get_table_description(
                cursor, table)
        ]
        if column in existing:
            return
        cursor.execute(
            'ALTER TABLE {} ADD COLUMN {} varchar(255) NULL'.format(table, column)
        )


class Migration(migrations.Migration):

    dependencies = [
        ('instagram_app', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_app_secret_if_missing, migrations.RunPython.noop),
    ]
