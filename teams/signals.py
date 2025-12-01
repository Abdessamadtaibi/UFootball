from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from .models import Club
from u13_backend.utils import delete_old_file_on_change, delete_file_on_delete

@receiver(pre_save, sender=Club)
def delete_club_logo_on_change(sender, instance, **kwargs):
    delete_old_file_on_change(sender, instance, 'logo')

@receiver(post_delete, sender=Club)
def delete_club_logo_on_delete(sender, instance, **kwargs):
    delete_file_on_delete(sender, instance, 'logo')
