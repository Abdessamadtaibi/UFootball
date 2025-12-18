from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import RegexValidator
import uuid

class User(AbstractUser):
    """
    Modèle utilisateur personnalisé pour l'application U13
    Supporte 3 types de profils : Parent, Staff, Admin/Organisateur
    """
    
    USER_TYPES = (
        ('parent', 'Parent'),
        ('staff', 'Staff'),
        ('admin', 'Admin/Organisateur'),
        ('viewer', 'Viewer'),  # Read-only access to tournaments and matches
    )
    
    # Champs de base
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    
    # Numéro de téléphone avec validation
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Le numéro de téléphone doit être au format: '+999999999'. Jusqu'à 15 chiffres autorisés."
    )
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    
    # Type d'utilisateur
    user_type = models.CharField(max_length=10, choices=USER_TYPES,blank=False,null=False)
    
    # Photo de profil
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    
    # Préférences de notifications
    notifications_match_updates = models.BooleanField(default=True)
    notifications_tournament_news = models.BooleanField(default=True)
    notifications_team_news = models.BooleanField(default=True)
    
    # Métadonnées
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Configuration pour l'authentification
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone_number','user_type','username', 'first_name', 'last_name']
    
    class Meta:
        db_table = 'users'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_user_type_display()})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def is_parent(self):
        return self.user_type == 'parent'
    
    def is_staff_member(self):
        return self.user_type == 'staff'
    
    def is_admin_user(self):
        return self.user_type == 'admin'
    
    def is_viewer(self):
        return self.user_type == 'viewer'


class UserProfile(models.Model):
    """
    Profil étendu pour les utilisateurs avec informations spécifiques selon le type
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Pour les parents
    children_names = models.TextField(blank=True, help_text="Noms des enfants séparés par des virgules")
    
    # Pour le staff
    coaching_license = models.CharField(max_length=100, blank=True)
    experience_years = models.PositiveIntegerField(null=True, blank=True)
    specialization = models.CharField(max_length=100, blank=True)
    
    # Pour les admins/organisateurs
    organization = models.CharField(max_length=200, blank=True)
    position = models.CharField(max_length=100, blank=True)
    
    # Informations générales
    bio = models.TextField(blank=True)
    address = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=100, blank=True)
    emergency_phone = models.CharField(max_length=17, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'Profil utilisateur'
        verbose_name_plural = 'Profils utilisateurs'
    
    def __str__(self):
        return f"Profil de {self.user.full_name}"
