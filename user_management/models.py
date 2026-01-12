from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    class Role(models.TextChoices):
        CONSULTANT = 'CONSULTANT', 'Consultant'
        CLIENT = 'CLIENT', 'Client'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENT)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    @property
    def is_consultant(self):
        return self.role == self.Role.CONSULTANT

    @property
    def is_client(self):
        return self.role == self.Role.CLIENT


class ConsultantClientLink(models.Model):
    """
    Strictly links a Consultant to a Client.
    A Client can potentially be managed by multiple Consultants? 
    For now, let's assume a Client belongs to a Consultant, but M2M is safer if shared.
    However, the plan implies rigid ownership. Let's stick to M2M or simple Link table.
    This Link table allows M2M conceptually but we can enforce uniqueness if needed.
    """
    consultant = models.ForeignKey(
        UserProfile, 
        on_delete=models.CASCADE, 
        related_name='clients_managed',
        limit_choices_to={'role': UserProfile.Role.CONSULTANT}
    )
    client = models.ForeignKey(
        UserProfile, 
        on_delete=models.CASCADE, 
        related_name='managed_by',
        limit_choices_to={'role': UserProfile.Role.CLIENT}
    )
    status = models.CharField(max_length=20, default='ACTIVE', choices=[
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive')
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('consultant', 'client')
        verbose_name = "Consultant-Client Link"
        verbose_name_plural = "Consultant-Client Links"

    def __str__(self):
        return f"{self.consultant.user.username} -> {self.client.user.username}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Default to CLIENT if not specified, but usually we create Profile explicitly in views
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
