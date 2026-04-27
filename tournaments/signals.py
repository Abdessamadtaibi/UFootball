from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from .models import Match, Tournament
from matches.models import Match as GlobalMatch
from u13_backend.utils import delete_old_file_on_change, delete_file_on_delete

@receiver(post_save, sender=Match)
def sync_match_to_global(sender, instance, created, **kwargs):
    """
    Sync Match to GlobalMatch (matches.Match)
    """
    # Do not sync placeholder matches that don't have both teams determined yet
    if not instance.home_team or not instance.away_team:
        return

    # Map status
    status_mapping = {
        'scheduled': 'scheduled',
        'live': 'live',
        'finished': 'finished',
        'postponed': 'postponed',
        'cancelled': 'cancelled',
    }
    
    # Map match_type from phase
    match_type = 'group_stage'
    if instance.phase:
        phase_type_mapping = {
            'group_stage': 'group_stage',
            'round_16': 'knockout',
            'quarter_final': 'quarter_final',
            'semi_final': 'semi_final',
            'final': 'final',
            'third_place': 'third_place',
        }
        match_type = phase_type_mapping.get(instance.phase.phase_type, 'group_stage')
    
    # Map fields
    match_data = {
        'tournament': instance.tournament,
        'phase': instance.phase,
        'group': instance.group,
        'home_team': instance.home_team,
        'away_team': instance.away_team,
        'scheduled_date': instance.match_date,
        'venue_name': instance.venue,
        'home_score': instance.home_score,
        'away_score': instance.away_score,
        'status': status_mapping.get(instance.status, 'scheduled'),
        'match_type': match_type,
    }

    # update or create
    # We use the same ID to link them
    GlobalMatch.objects.update_or_create(
        id=instance.id,
        defaults=match_data
    )

@receiver(post_delete, sender=Match)
def delete_global_match(sender, instance, **kwargs):
    """
    Delete GlobalMatch when Match is deleted
    """
    try:
        GlobalMatch.objects.get(id=instance.id).delete()
    except GlobalMatch.DoesNotExist:
        pass

@receiver(pre_save, sender=Tournament)
def delete_tournament_images_on_change(sender, instance, **kwargs):
    delete_old_file_on_change(sender, instance, 'logo')
    delete_old_file_on_change(sender, instance, 'banner_image')

@receiver(post_delete, sender=Tournament)
def delete_tournament_images_on_delete(sender, instance, **kwargs):
    delete_file_on_delete(sender, instance, 'logo')
    delete_file_on_delete(sender, instance, 'banner_image')


@receiver(pre_save, sender=Match)
def track_match_status_change(sender, instance, **kwargs):
    """Track if status changed to 'finished'."""
    if instance.pk:
        try:
            old = Match.objects.get(pk=instance.pk)
            instance._status_changed_to_finished = (
                old.status != 'finished' and instance.status == 'finished'
            )
        except Match.DoesNotExist:
            instance._status_changed_to_finished = False
    else:
        instance._status_changed_to_finished = False


@receiver(post_save, sender=Match)
def handle_match_finished(sender, instance, **kwargs):
    """
    When a match is marked as finished:
    1. Propagate winner to next knockout match
    2. Check if group stage is complete → auto-generate knockout
    3. Check if league is complete → determine winner
    """
    if not getattr(instance, '_status_changed_to_finished', False):
        return

    from .services import TournamentEngine
    tournament = instance.tournament
    engine = TournamentEngine(tournament)

    # 1. If it's a knockout match, propagate the winner
    if instance.is_knockout:
        TournamentEngine.propagate_winner(instance)

    # 2. If it's a group match, check if group stage is complete
    elif instance.group:
        if tournament.tournament_type == 'group_knockout':
            engine.check_group_stage_and_generate_knockout()
        elif tournament.tournament_type == 'league':
            engine.determine_league_winner()