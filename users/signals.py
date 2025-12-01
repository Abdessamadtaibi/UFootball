from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from u13_backend.utils import delete_old_file_on_change, delete_file_on_delete

User = get_user_model()

@receiver(pre_save, sender=User)
def delete_user_profile_picture_on_change(sender, instance, **kwargs):
    delete_old_file_on_change(sender, instance, 'profile_picture')

@receiver(post_delete, sender=User)
def delete_user_profile_picture_on_delete(sender, instance, **kwargs):
    delete_file_on_delete(sender, instance, 'profile_picture')
