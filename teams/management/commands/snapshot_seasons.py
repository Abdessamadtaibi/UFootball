"""
Management command: snapshot_seasons

Populates data (roster, stats, tournament results) for all existing seasons
that are missing their snapshots.
"""
from django.core.management.base import BaseCommand
from teams.models import Season
from teams.season_stats import snapshot_season_data


class Command(BaseCommand):
    help = 'Snapshot team/player data into all existing seasons that have empty data.'

    def handle(self, *args, **options):
        seasons = Season.objects.select_related('team').filter(team__isnull=False)
        total = seasons.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS('No seasons found.'))
            return

        filled_count = 0
        for season in seasons:
            team = season.team
            has_roster = season.player_roster.exists()
            has_stats = hasattr(season, 'team_stats') and season.team_stats is not None

            try:
                _ = season.team_stats
                has_stats = True
            except Exception:
                has_stats = False

            if not has_roster or not has_stats:
                snapshot_season_data(season)
                players_count = season.player_roster.count()
                filled_count += 1
                self.stdout.write(
                    f'  ✓ {team.name} – {season.name} '
                    f'[{players_count} players, stats snapshotted]'
                )
            else:
                self.stdout.write(f'  · {team.name} – {season.name} (already has data)')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Filled data for {filled_count}/{total} season(s).'
        ))
