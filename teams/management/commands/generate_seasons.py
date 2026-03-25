"""
Management command: generate_seasons

Creates seasons automatically for all teams that don't have any season yet,
based on each team's sport and created_at date.
Snapshots current team/player data into each created season.
"""
from django.core.management.base import BaseCommand
from teams.models import Team, Season
from teams.season_calendar import get_season_for_team
from teams.season_stats import snapshot_season_data


class Command(BaseCommand):
    help = 'Generate seasons for existing teams that have no season, and snapshot their data.'

    def handle(self, *args, **options):
        teams_without_season = Team.objects.filter(seasons__isnull=True)
        total = teams_without_season.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS('All teams already have seasons. Nothing to do.'))
            return

        created_count = 0
        for team in teams_without_season:
            ref_date = team.created_at.date() if hasattr(team.created_at, 'date') else team.created_at
            season_name, start_date, end_date = get_season_for_team(team, ref_date)

            season, was_created = Season.objects.get_or_create(
                team=team,
                name=season_name,
                defaults={
                    'start_date': start_date,
                    'end_date': end_date,
                },
            )

            # Link the season to the team
            if team.season != season:
                Team.objects.filter(pk=team.pk).update(season=season)

            if was_created:
                # Snapshot team/player data into the season
                snapshot_season_data(season)
                players_count = team.players.filter(is_active=True).count()
                created_count += 1
                self.stdout.write(
                    f'  ✓ {team.name} ({team.sport}) → {season_name} '
                    f'[{players_count} players snapshotted]'
                )

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Created {created_count} season(s) for {total} team(s) with data snapshots.'
        ))
