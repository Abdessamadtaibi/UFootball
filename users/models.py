from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.core.validators import RegexValidator
import uuid


class UserManager(BaseUserManager):
    """
    Custom manager for User model that uses email as the primary identifier
    instead of username.
    """

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        # Auto-populate username from email if not provided
        if not extra_fields.get('username'):
            extra_fields['username'] = email
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Modèle utilisateur personnalisé pour l'application U13
    Supporte 3 types de profils : Parent, Staff, Admin/Organisateur
    """
    
    USER_TYPES = (
        ('parent', 'Parent'),
        ('coach', 'Coach'),
        ('staff', 'Staff'),
        ('admin', 'Admin/Organisateur'),
        ('viewer', 'Viewer'),
    )
    
    # Custom manager
    objects = UserManager()

    # Champs de base
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Override username from AbstractUser: make it optional (email is used for login)
    username = models.CharField(max_length=150, blank=True, default='')
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
    is_admin_approved = models.BooleanField(
        default=False,
        help_text="Required for admin/organizer accounts. Must be approved by UFootball team before login is allowed."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Configuration pour l'authentification
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'user_type']
    
    class Meta:
        db_table = 'users'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
    
    def save(self, *args, **kwargs):
        # Auto-populate username from email if not set
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

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
    
    def is_coach(self):
        return self.user_type == 'coach'
    
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
