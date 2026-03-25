from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .models import Club, Team, Player, Season
from u13_backend.utils import delete_old_file_on_change, delete_file_on_delete


@receiver(pre_save, sender=Club)
def delete_club_logo_on_change(sender, instance, **kwargs):
    delete_old_file_on_change(sender, instance, 'logo')


@receiver(post_delete, sender=Club)
def delete_club_logo_on_delete(sender, instance, **kwargs):
    delete_file_on_delete(sender, instance, 'logo')


# ─────────────────────────────────────────────
# Auto-create season on Team creation
# ─────────────────────────────────────────────

@receiver(post_save, sender=Team)
def auto_create_season_for_team(sender, instance, created, **kwargs):
    """Auto-create a Season based on the team's sport when a new team is created."""
    if not created:
        return

    from .season_calendar import get_season_for_team
    from .season_stats import snapshot_season_data

    season_name, start_date, end_date = get_season_for_team(instance)

    season, was_created = Season.objects.get_or_create(
        team=instance,
        name=season_name,
        defaults={
            'start_date': start_date,
            'end_date': end_date,
        },
    )

    # Link the season to the team
    if instance.season != season:
        Team.objects.filter(pk=instance.pk).update(season=season)

    # Snapshot team/player data into the season
    if was_created:
        snapshot_season_data(season)


# ─────────────────────────────────────────────
# Auto-sync Team stats → active SeasonTeamStats
# ─────────────────────────────────────────────

# Fields on Team that should be synced to SeasonTeamStats
_TEAM_STAT_FIELDS = {
    'matches_played', 'matches_won', 'matches_drawn', 'matches_lost',
    'goals_for', 'goals_against', 'trophies_won',
}


@receiver(post_save, sender=Team)
def sync_team_stats_to_season(sender, instance, created, **kwargs):
    """When Team stats change, update the active season's SeasonTeamStats."""
    if created:
        return  # Handled by auto_create_season_for_team

    from .models import SeasonTeamStats

    # Find the active season for this team
    active_season = Season.objects.filter(
        team=instance, is_active=True
    ).first()
    if not active_season:
        # Fallback: use the team's linked season
        active_season = instance.season
    if not active_season:
        return

    # Update or create SeasonTeamStats
    stats, _ = SeasonTeamStats.objects.get_or_create(
        season=active_season, team=instance,
    )
    stats.matches_played = instance.matches_played
    stats.matches_won = instance.matches_won
    stats.matches_drawn = instance.matches_drawn
    stats.matches_lost = instance.matches_lost
    stats.goals_for = instance.goals_for
    stats.goals_against = instance.goals_against
    stats.trophies_won = instance.trophies_won
    stats.save()


# ─────────────────────────────────────────────
# Auto-sync Player stats → active SeasonPlayerStats + Roster
# ─────────────────────────────────────────────

@receiver(post_save, sender=Player)
def sync_player_stats_to_season(sender, instance, **kwargs):
    """When Player stats change, update the active season's data."""
    from .models import SeasonPlayerStats, SeasonPlayerRoster

    team = instance.team
    if not team:
        return

    # Find the active season
    active_season = Season.objects.filter(
        team=team, is_active=True
    ).first()
    if not active_season:
        active_season = team.season
    if not active_season:
        return

    # Update SeasonPlayerStats
    player_stats, _ = SeasonPlayerStats.objects.get_or_create(
        season=active_season, player=instance,
    )
    player_stats.goals_scored = instance.goals_scored
    player_stats.assists = instance.assists
    player_stats.yellow_cards = instance.yellow_cards
    player_stats.red_cards = instance.red_cards
    player_stats.minutes_played = instance.minutes_played
    player_stats.save()

    # Update SeasonPlayerRoster (keep roster in sync)
    if instance.is_active:
        SeasonPlayerRoster.objects.update_or_create(
            season=active_season,
            player=instance,
            defaults={
                'first_name': instance.first_name,
                'last_name': instance.last_name,
                'birth_date': instance.birth_date,
                'jersey_number': instance.jersey_number,
                'position': instance.position or '',
                'is_captain': instance.is_captain,
                'is_main_player': instance.is_main_player,
                'status': instance.status,
            },
        )

