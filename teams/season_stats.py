"""
Helper functions to update season stats automatically when matches finish.
Called from matches/views.py when a match status changes to 'finished'.
"""
from django.db.models import Avg, Sum, Q, F
from django.db import transaction


def update_season_stats_for_match(match):
    """
    Update SeasonTeamStats, SeasonPlayerStats, and SeasonTournamentResult
    when a match finishes. Called after a match status → 'finished'.
    """
    from teams.models import Season, SeasonTeamStats, SeasonPlayerStats, SeasonTournamentResult
    from matches.models import MatchLineup, MatchEvent

    match_date = match.scheduled_date.date() if match.scheduled_date else None
    if not match_date:
        return

    for team, goals_scored, goals_conceded in [
        (match.home_team, match.home_score, match.away_score),
        (match.away_team, match.away_score, match.home_score),
    ]:
        # Find the season for this team that covers the match date
        season = Season.objects.filter(
            team=team,
            start_date__lte=match_date,
            end_date__gte=match_date,
        ).first()

        # Fallback: use the team's linked season
        if not season:
            season = team.season
        if not season:
            continue

        # ── Update SeasonTeamStats ──────────────────────────
        _update_team_stats(season, team, goals_scored, goals_conceded, match)

        # ── Update SeasonPlayerStats ────────────────────────
        _update_player_stats(season, team, match)

        # ── Update SeasonTournamentResult ───────────────────
        if match.tournament:
            _update_tournament_result(season, team, match, goals_scored, goals_conceded)


@transaction.atomic
def _update_team_stats(season, team, goals_scored, goals_conceded, match):
    """Increment team stats for this match."""
    from teams.models import SeasonTeamStats

    stats, _created = SeasonTeamStats.objects.get_or_create(
        season=season,
        team=team,
    )

    stats.matches_played = F('matches_played') + 1
    stats.goals_for = F('goals_for') + goals_scored
    stats.goals_against = F('goals_against') + goals_conceded

    if goals_scored > goals_conceded:
        stats.matches_won = F('matches_won') + 1
    elif goals_scored == goals_conceded:
        stats.matches_drawn = F('matches_drawn') + 1
    else:
        stats.matches_lost = F('matches_lost') + 1

    if goals_conceded == 0:
        stats.clean_sheets = F('clean_sheets') + 1

    # Sum cards from MatchEvents for this team in this match
    from matches.models import MatchEvent
    team_events = MatchEvent.objects.filter(match=match, team=team)
    yellows = team_events.filter(event_type='yellow_card').count()
    reds = team_events.filter(event_type='red_card').count()
    if yellows:
        stats.yellow_cards = F('yellow_cards') + yellows
    if reds:
        stats.red_cards = F('red_cards') + reds

    stats.save()


@transaction.atomic
def _update_player_stats(season, team, match):
    """Update per-player stats from MatchLineup data for this match."""
    from teams.models import SeasonPlayerStats
    from matches.models import MatchLineup

    lineups = MatchLineup.objects.filter(match=match, team=team).select_related('player')

    for lineup in lineups:
        player_stats, _created = SeasonPlayerStats.objects.get_or_create(
            season=season,
            player=lineup.player,
        )

        player_stats.matches_played = F('matches_played') + 1
        if lineup.is_starter:
            player_stats.matches_started = F('matches_started') + 1
        player_stats.minutes_played = F('minutes_played') + lineup.minutes_played
        player_stats.goals_scored = F('goals_scored') + lineup.goals_scored
        player_stats.assists = F('assists') + lineup.assists
        player_stats.yellow_cards = F('yellow_cards') + lineup.yellow_cards
        player_stats.red_cards = F('red_cards') + lineup.red_cards
        player_stats.save()

    # Recalculate average ratings for players who have ratings
    _recalculate_average_ratings(season, team)


def _recalculate_average_ratings(season, team):
    """Recalculate average_rating from all MatchLineup ratings in the season."""
    from teams.models import SeasonPlayerStats
    from matches.models import MatchLineup, Match

    player_stats = SeasonPlayerStats.objects.filter(
        season=season,
        player__team=team,
    )
    for ps in player_stats:
        avg = MatchLineup.objects.filter(
            player=ps.player,
            match__scheduled_date__date__gte=season.start_date,
            match__scheduled_date__date__lte=season.end_date,
            match__status='finished',
            rating__isnull=False,
        ).aggregate(avg_rating=Avg('rating'))['avg_rating']

        if avg is not None:
            ps.average_rating = round(avg, 1)
            ps.save(update_fields=['average_rating', 'updated_at'])


@transaction.atomic
def _update_tournament_result(season, team, match, goals_scored, goals_conceded):
    """Update tournament-specific results within the season."""
    from teams.models import SeasonTournamentResult

    result, _created = SeasonTournamentResult.objects.get_or_create(
        season=season,
        team=team,
        tournament=match.tournament,
    )

    result.matches_played = F('matches_played') + 1
    result.goals_for = F('goals_for') + goals_scored
    result.goals_against = F('goals_against') + goals_conceded

    if goals_scored > goals_conceded:
        result.matches_won = F('matches_won') + 1
    elif goals_scored == goals_conceded:
        result.matches_drawn = F('matches_drawn') + 1
    else:
        result.matches_lost = F('matches_lost') + 1

    # Calculate points based on tournament scoring rules
    tournament = match.tournament
    if goals_scored > goals_conceded:
        result.points = F('points') + tournament.points_per_win
    elif goals_scored == goals_conceded:
        result.points = F('points') + tournament.points_per_draw
    else:
        result.points = F('points') + tournament.points_per_loss

    # Fill in group info if available
    if match.group:
        result.group_name = match.group.name

    result.save()


def recalculate_season_stats(season):
    """
    Full recalculation of all season stats from scratch.
    Useful if match data was manually edited.
    """
    from teams.models import SeasonTeamStats, SeasonPlayerStats, SeasonTournamentResult
    from matches.models import Match, MatchLineup, MatchEvent
    from django.db.models import Q

    team = season.team
    if not team:
        return

    # Clear existing stats
    SeasonTeamStats.objects.filter(season=season).delete()
    SeasonPlayerStats.objects.filter(season=season).delete()
    SeasonTournamentResult.objects.filter(season=season).delete()

    # Find all finished matches for this team in the season date range
    matches = Match.objects.filter(
        Q(home_team=team) | Q(away_team=team),
        scheduled_date__date__gte=season.start_date,
        scheduled_date__date__lte=season.end_date,
        status='finished',
    ).select_related('home_team', 'away_team', 'tournament')

    for match in matches:
        if match.home_team == team:
            goals_scored = match.home_score
            goals_conceded = match.away_score
        else:
            goals_scored = match.away_score
            goals_conceded = match.home_score

        _update_team_stats(season, team, goals_scored, goals_conceded, match)
        _update_player_stats(season, team, match)
        if match.tournament:
            _update_tournament_result(season, team, match, goals_scored, goals_conceded)


@transaction.atomic
def snapshot_season_data(season):
    """
    Snapshot current team/player/tournament data into the season's related models.
    Called when a season is first created (signal or management command).
    Also triggers recalculate_season_stats to pull in match-level data.
    """
    from teams.models import (
        SeasonTeamStats, SeasonPlayerStats, SeasonPlayerRoster,
        SeasonTournamentResult, TeamTournamentRegistration,
    )

    team = season.team
    if not team:
        return

    # ── 1. SeasonTeamStats — snapshot from Team model ──────────
    SeasonTeamStats.objects.get_or_create(
        season=season,
        team=team,
        defaults={
            'matches_played': team.matches_played,
            'matches_won': team.matches_won,
            'matches_drawn': team.matches_drawn,
            'matches_lost': team.matches_lost,
            'goals_for': team.goals_for,
            'goals_against': team.goals_against,
            'trophies_won': team.trophies_won,
        },
    )

    # ── 2. SeasonPlayerRoster — snapshot player identities ─────
    players = team.players.filter(is_active=True)
    for player in players:
        SeasonPlayerRoster.objects.get_or_create(
            season=season,
            player=player,
            defaults={
                'first_name': player.first_name,
                'last_name': player.last_name,
                'birth_date': player.birth_date,
                'jersey_number': player.jersey_number,
                'position': player.position or '',
                'is_captain': player.is_captain,
                'is_main_player': player.is_main_player,
                'status': player.status,
            },
        )

    # ── 3. SeasonPlayerStats — snapshot from Player model ──────
    for player in players:
        SeasonPlayerStats.objects.get_or_create(
            season=season,
            player=player,
            defaults={
                'goals_scored': player.goals_scored,
                'assists': player.assists,
                'yellow_cards': player.yellow_cards,
                'red_cards': player.red_cards,
                'minutes_played': player.minutes_played,
            },
        )

    # ── 4. SeasonTournamentResult — from registrations ─────────
    registrations = TeamTournamentRegistration.objects.filter(
        team=team, status='confirmed'
    ).select_related('tournament', 'group')
    for reg in registrations:
        SeasonTournamentResult.objects.get_or_create(
            season=season,
            team=team,
            tournament=reg.tournament,
            defaults={
                'points': reg.tournament_points,
                'matches_played': reg.tournament_matches_played,
                'matches_won': reg.tournament_matches_won,
                'matches_drawn': reg.tournament_matches_drawn,
                'matches_lost': reg.tournament_matches_lost,
                'goals_for': reg.tournament_goals_for,
                'goals_against': reg.tournament_goals_against,
                'group_name': reg.group.name if reg.group else '',
            },
        )

    # ── 5. Recalculate from match data (overrides team-level snapshot) ──
    try:
        recalculate_season_stats(season)
    except Exception:
        # If matches app isn't ready or no matches exist, that's fine —
        # we still have the team-level snapshot from step 1.
        pass
