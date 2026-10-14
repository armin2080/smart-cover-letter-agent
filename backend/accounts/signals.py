"""Signals ensuring every user has the related default rows."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, ensure_user_defaults


@receiver(post_save, sender=User)
def create_user_defaults(sender, instance: User, created: bool, **kwargs) -> None:
    if created:
        ensure_user_defaults(instance)
