# Custom migration to handle Sport->Club, Season->Team, Coach->Team

import django.db.models.deletion
from django.db import migrations, models


def safe_drop_column(apps, schema_editor):
    """Safely drop club_id columns that may or may not exist,
    depending on whether a previous partial migration already removed them."""
    connection = schema_editor.connection
    cursor = connection.cursor()

    # Check and drop club_id from coaches
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = 'coaches' AND column_name = 'club_id'"
    )
    if cursor.fetchone()[0] > 0:
        # Drop FK constraint first
        cursor.execute(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE table_schema = DATABASE() AND table_name = 'coaches' "
            "AND column_name = 'club_id' AND REFERENCED_TABLE_NAME IS NOT NULL"
        )
        for row in cursor.fetchall():
            cursor.execute(f"ALTER TABLE coaches DROP FOREIGN KEY `{row[0]}`")
        # Drop index if exists
        cursor.execute(
            "SELECT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE table_schema = DATABASE() AND table_name = 'coaches' AND column_name = 'club_id'"
        )
        for row in cursor.fetchall():
            try:
                cursor.execute(f"ALTER TABLE coaches DROP INDEX `{row[0]}`")
            except Exception:
                pass
        cursor.execute("ALTER TABLE coaches DROP COLUMN club_id")

    # Check and drop unique_together on seasons (club, name) if it exists
    cursor.execute(
        "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE table_schema = DATABASE() AND table_name = 'seasons' "
        "AND constraint_type = 'UNIQUE'"
    )
    for row in cursor.fetchall():
        try:
            cursor.execute(f"ALTER TABLE seasons DROP INDEX `{row[0]}`")
        except Exception:
            pass

    # Check and drop club_id from seasons
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = 'seasons' AND column_name = 'club_id'"
    )
    if cursor.fetchone()[0] > 0:
        cursor.execute(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE table_schema = DATABASE() AND table_name = 'seasons' "
            "AND column_name = 'club_id' AND REFERENCED_TABLE_NAME IS NOT NULL"
        )
        for row in cursor.fetchall():
            cursor.execute(f"ALTER TABLE seasons DROP FOREIGN KEY `{row[0]}`")
        cursor.execute(
            "SELECT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE table_schema = DATABASE() AND table_name = 'seasons' AND column_name = 'club_id'"
        )
        for row in cursor.fetchall():
            try:
                cursor.execute(f"ALTER TABLE seasons DROP INDEX `{row[0]}`")
            except Exception:
                pass
        cursor.execute("ALTER TABLE seasons DROP COLUMN club_id")


class Migration(migrations.Migration):

    dependencies = [
        ("teams", "0006_remove_player_father_first_name_and_more"),
    ]

    operations = [
        # Step 1: Use SeparateDatabaseAndState to safely remove old columns
        # The RunPython handles the actual DB changes (with existence checks),
        # while state_operations tell Django what model changes happened.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(safe_drop_column, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="coach",
                    name="club",
                ),
                migrations.AlterUniqueTogether(
                    name="season",
                    unique_together=set(),
                ),
                migrations.RemoveField(
                    model_name="season",
                    name="club",
                ),
            ],
        ),

        # Step 2: Add team FK to coach
        migrations.AddField(
            model_name="coach",
            name="team",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="coaches",
                to="teams.team",
                verbose_name="Équipe",
            ),
        ),

        # Step 3: Add team FK to season
        migrations.AddField(
            model_name="season",
            name="team",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="seasons",
                to="teams.team",
                verbose_name="Équipe",
            ),
        ),

        # Step 4: Add club FK to sport
        migrations.AddField(
            model_name="sport",
            name="club",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sports",
                to="teams.club",
                verbose_name="Club",
            ),
        ),

        # Step 5: Set new unique_together for season
        migrations.AlterUniqueTogether(
            name="season",
            unique_together={("team", "name")},
        ),
    ]
