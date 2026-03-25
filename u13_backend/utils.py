from django.db import models

def delete_old_file_on_change(sender, instance, field_name, **kwargs):
    """
    Deletes the old file from filesystem when corresponding object is updated with a new file.
    """
    if not instance.pk:
        return False

    try:
        old_obj = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return False

    old_file = getattr(old_obj, field_name)
    new_file = getattr(instance, field_name)

    if not old_file:
        return False

    if not new_file or old_file != new_file:
        old_file.delete(save=False)

def delete_file_on_delete(sender, instance, field_name, **kwargs):
    """
    Deletes the file from filesystem when corresponding object is deleted.
    """
    file = getattr(instance, field_name)
    if file:
        file.delete(save=False)
