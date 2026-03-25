from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from .models import Match as TournamentMatch, Tournament
from matches.models import Match as GlobalMatch
from u13_backend.utils import delete_old_file_on_change, delete_file_on_delete

@receiver(post_save, sender=TournamentMatch)
def sync_match_to_global(sender, instance, created, **kwargs):
    """
    Sync TournamentMatch to GlobalMatch (matches.Match)
    """
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

@receiver(post_delete, sender=TournamentMatch)
def delete_global_match(sender, instance, **kwargs):
    """
    Delete GlobalMatch when TournamentMatch is deleted
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
