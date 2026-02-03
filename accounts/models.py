from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with profile fields for cover letter generation."""
    
    experience = models.TextField(blank=True, default='')
    skills = models.JSONField(default=list, blank=True)
    certificates = models.JSONField(default=list, blank=True)
    preferred_jobs = models.TextField(blank=True, default='')
    
    def __str__(self):
        return self.username
