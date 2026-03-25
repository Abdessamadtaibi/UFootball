"""
Sport-based season calendar configuration.
Defines start/end months per sport and provides helpers to compute season dates.
"""
from datetime import date

# (start_month, end_month) — if end_month < start_month the season crosses years.
SPORT_SEASON_MONTHS = {
    'football':   (8, 6),    # August → June
    'basketball': (10, 6),   # October → June
    'handball':   (9, 6),    # September → June
    'volleyball': (10, 5),   # October → May
    'rugby':      (9, 6),    # September → June
    'tennis':     (1, 12),   # January → December
    'golf':       (3, 11),   # March → November
    'swimming':   (9, 7),    # September → July
    'athletics':  (10, 8),   # October → August
    'other':      (9, 6),    # September → June (default)
}


def _last_day_of_month(year, month):
    """Return the last day of a given month/year."""
    import calendar
    return calendar.monthrange(year, month)[1]


def get_season_for_team(team, reference_date=None):
    """
    Compute the season name and date range for a team based on its sport.

    Args:
        team: Team model instance (must have .sport and .created_at)
        reference_date: The date to use for determining which season year.
                        Defaults to team.created_at.date().

    Returns:
        (name, start_date, end_date)
        e.g. ("2025-2026", date(2025,8,1), date(2026,6,30))
    """
    if reference_date is None:
        reference_date = team.created_at.date() if hasattr(team.created_at, 'date') else team.created_at

    sport = team.sport or 'other'
    start_month, end_month = SPORT_SEASON_MONTHS.get(sport, (9, 6))

    crosses_year = end_month < start_month

    if crosses_year:
        # Season spans two calendar years (e.g. Aug 2025 → Jun 2026)
        if reference_date.month >= start_month:
            # We are in the first half of the season (e.g. Aug-Dec)
            start_year = reference_date.year
        else:
            # We are in the second half (e.g. Jan-Jun), season started last year
            start_year = reference_date.year - 1

        end_year = start_year + 1
        season_name = f"{start_year}-{end_year}"
        start_date = date(start_year, start_month, 1)
        end_date = date(end_year, end_month, _last_day_of_month(end_year, end_month))
    else:
        # Season within the same calendar year (e.g. Jan → Dec)
        start_year = reference_date.year
        season_name = str(start_year)
        start_date = date(start_year, start_month, 1)
        end_date = date(start_year, end_month, _last_day_of_month(start_year, end_month))

    return season_name, start_date, end_date
