from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Match, MatchLineup


@receiver(pre_save, sender=MatchLineup)
def update_player_stats_on_lineup_change(sender, instance, **kwargs):
    """
    Automatically update player's overall statistics when lineup stats change.
    This ensures that when staff updates player stats in a match lineup,
    the player's career statistics are automatically updated.
    """
    if instance.pk:  # Only for updates, not new records
        try:
            # Get the old values before saving
            old_lineup = MatchLineup.objects.get(pk=instance.pk)
            
            # Calculate the difference in stats
            goals_diff = instance.goals_scored - old_lineup.goals_scored
            assists_diff = instance.assists - old_lineup.assists
            yellow_cards_diff = instance.yellow_cards - old_lineup.yellow_cards
            red_cards_diff = instance.red_cards - old_lineup.red_cards
            minutes_diff = instance.minutes_played - old_lineup.minutes_played
            
            # Update player's overall statistics
            player = instance.player
            player.goals_scored = (player.goals_scored or 0) + goals_diff
            player.assists = (player.assists or 0) + assists_diff
            player.yellow_cards = (player.yellow_cards or 0) + yellow_cards_diff
            player.red_cards = (player.red_cards or 0) + red_cards_diff
            player.minutes_played = (player.minutes_played or 0) + minutes_diff
            
            # Ensure no negative values
            player.goals_scored = max(0, player.goals_scored)
            player.assists = max(0, player.assists)
            player.yellow_cards = max(0, player.yellow_cards)
            player.red_cards = max(0, player.red_cards)
            player.minutes_played = max(0, player.minutes_played)
            
            player.save()
        except MatchLineup.DoesNotExist:
            pass


@receiver(post_save, sender=Match)
def auto_sync_match_to_season(sender, instance, **kwargs):
    """
    When a finished match is saved (scores updated), recalculate the
    season stats for both teams involved.
    """
    if instance.status != 'finished':
        return

    try:
        from teams.season_stats import recalculate_season_stats
        from teams.models import Season

        for team in [instance.home_team, instance.away_team]:
            match_date = instance.scheduled_date.date() if instance.scheduled_date else None

            # Find the season by date range
            season = None
            if match_date:
                season = Season.objects.filter(
                    team=team,
                    start_date__lte=match_date,
                    end_date__gte=match_date,
                ).first()

            # Fallback: team's linked season
            if not season:
                season = team.season
            if not season:
                continue

            recalculate_season_stats(season)
    except Exception:
        pass  # Don't break match save if stats update fails


@receiver(post_save, sender=MatchLineup)
def auto_sync_lineup_to_season(sender, instance, **kwargs):
    """
    When a MatchLineup is saved, sync the player's season stats from the
    match data to ensure the season stays up-to-date.
    """
    match = instance.match
    if match.status != 'finished':
        return

    try:
        from teams.season_stats import recalculate_season_stats
        from teams.models import Season

        team = instance.team
        match_date = match.scheduled_date.date() if match.scheduled_date else None

        season = None
        if match_date:
            season = Season.objects.filter(
                team=team,
                start_date__lte=match_date,
                end_date__gte=match_date,
            ).first()
        if not season:
            season = team.season
        if not season:
            return

        recalculate_season_stats(season)
    except Exception:
        pass
