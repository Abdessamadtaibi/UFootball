from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from tournaments.models import Tournament, TournamentGroup

User = get_user_model() 


class Club(models.Model):

    name = models.CharField(max_length=200, verbose_name="Nom du club",unique=True)
    short_name = models.CharField(max_length=10, verbose_name="Nom court", help_text="Ex: PSG, OM",unique=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_clubs',
        verbose_name='Propriétaire'
    )
    
    # Informations visuelles
    logo = models.ImageField(upload_to='club_logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default="#000000", help_text="Couleur principale (hex)")
    secondary_color = models.CharField(max_length=7, default="#FFFFFF", help_text="Couleur secondaire (hex)")
    
    # Informations de contact
    address = models.TextField(verbose_name="Adresse")
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    
    # Informations administratives
    license_number = models.CharField(max_length=50, blank=True, verbose_name="Numéro de licence")
    founded_year = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1800), MaxValueValidator(2030)])
    
    # Métadonnées
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'clubs'
        verbose_name = 'Club'
        verbose_name_plural = 'Clubs'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Team(models.Model):
    
    CATEGORY_CHOICES = (
        ('u10', 'U10'),
        ('u11', 'U11'),
        ('u12', 'U12'),
        ('u13', 'U13'),
        ('u14', 'U14'),
        ('u15', 'U15'),
        ('u16', 'U16'),
        ('u17', 'U17'),
        ('u18', 'U18'),
        ('u19', 'U19'),
        ('u20', 'U20'),
        ('u21', 'U21')
    )
    
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=200, verbose_name="Nom de l'équipe")
    category = models.CharField(max_length=5, choices=CATEGORY_CHOICES, default='u13')
    
    # Staff technique
    coach = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='coached_teams')
    assistant_coaches = models.ManyToManyField(User, blank=True, related_name='assistant_coached_teams')
    # Parents who follow this team (access to team statistics and matches)
    followers = models.ManyToManyField(User, blank=True, related_name='followed_teams')
    
    # Tournois
    tournaments = models.ManyToManyField(Tournament, through='TeamTournamentRegistration', related_name='teams')
    
    # Palmarès et statistiques
    trophies_won = models.PositiveIntegerField(default=0, verbose_name="Trophées remportés")
    matches_played = models.PositiveIntegerField(default=0)
    matches_won = models.PositiveIntegerField(default=0)
    matches_drawn = models.PositiveIntegerField(default=0)
    matches_lost = models.PositiveIntegerField(default=0)
    goals_for = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)
    
    # Métadonnées
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'teams'
        verbose_name = 'Équipe'
        verbose_name_plural = 'Équipes'
        ordering = ['club__name', 'name']
        unique_together = ['club', 'name', 'category']
    
    def __str__(self):
        return f"{self.club.name} - {self.name}"
    
    @property
    def full_name(self):
        return f"{self.club.name} {self.name}"
    
    @property
    def goal_difference(self):
        return self.goals_for - self.goals_against
    
    @property
    def points(self):
        return (self.matches_won * 3) + self.matches_drawn


class Player(models.Model):
    """
    Modèle pour les joueurs U13
    """
    
    POSITION_CHOICES = [
        ('GB', 'Goalkeeper'),
        ('DG', 'Left Back'),
        ('DC', 'Center Back'),
        ('DD', 'Right Back'),
        ('MDC', 'Defensive Mid'),
        ('MC', 'Central Mid'),
        ('MD', 'Right Mid'),
        ('MG', 'Left Mid'),
        ('AD', 'Right Winger'),
        ('AG', 'Left Winger'),
        ('AC', 'Striker'),
        ('ATT', 'Forward'),
    ]
    
    # Informations personnelles
    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    birth_date = models.DateField(verbose_name="Date de naissance")
    
    # Informations sportives
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='players')
    jersey_number = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(99)])
    position = models.CharField(max_length=3, choices=POSITION_CHOICES)
    is_captain = models.BooleanField(default=False, verbose_name="Capitaine")
    
    # NEW FIELD: Main player (starting 11)
    is_main_player = models.BooleanField(
        default=False, 
        verbose_name="Joueur titulaire",
        help_text="Fait partie des 11 joueurs principaux de l'équipe"
    )
    
    # Informations physiques
    height = models.PositiveIntegerField(null=True, blank=True, help_text="Taille en cm")
    weight = models.PositiveIntegerField(null=True, blank=True, help_text="Poids en kg")
    
    # Photo
    photo = models.ImageField(upload_to='player_photos/', blank=True, null=True)
    
    # Statistiques
    goals_scored = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)
    yellow_cards = models.PositiveIntegerField(default=0)
    red_cards = models.PositiveIntegerField(default=0)
    minutes_played = models.PositiveIntegerField(default=0)
     
    # Informations de contact (parents)
    parent_name = models.CharField(max_length=200, blank=True, verbose_name="Nom du parent/tuteur")
    parent_phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone du parent")
    parent_email = models.EmailField(blank=True, verbose_name="Email du parent")
    
    # Second parent/guardian contact info
    parent2_name = models.CharField(max_length=200, blank=True, verbose_name="Nom du 2ème parent/tuteur")
    parent2_phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone du 2ème parent")
    parent2_email = models.EmailField(blank=True, verbose_name="Email du 2ème parent")
    
    # Métadonnées
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'players'
        verbose_name = 'Joueur'
        verbose_name_plural = 'Joueurs'
        ordering = ['team', 'jersey_number']
        unique_together = ['team', 'jersey_number']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} (#{self.jersey_number})"
    
    def clean(self):
        """Validate that a team doesn't exceed 11 main players"""
        super().clean()
        
        if self.is_main_player:
            # Count current main players in the team (excluding this player if updating)
            main_players_count = Player.objects.filter(
                team=self.team,
                is_main_player=True,
                is_active=True
            ).exclude(pk=self.pk).count()
            
            if main_players_count >= 11:
                raise ValidationError({
                    'is_main_player': f'Cette équipe a déjà 11 joueurs titulaires. Vous devez d\'abord retirer un joueur titulaire.'
                })
    
    def save(self, *args, **kwargs):
        """Override save to call clean"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        from datetime import date
        today = date.today()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

class TeamTournamentRegistration(models.Model):
    """
    Inscription d'une équipe à un tournoi
    """
    
    STATUS_CHOICES = (
        ('pending', 'En attente'),
        ('confirmed', 'Confirmée'),
        ('rejected', 'Refusée'),
        ('withdrawn', 'Retirée'),
    )
    
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    group = models.ForeignKey(TournamentGroup, on_delete=models.SET_NULL, null=True, blank=True)
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    registration_date = models.DateTimeField(auto_now_add=True)
    confirmation_date = models.DateTimeField(null=True, blank=True)
    
    # Informations spécifiques au tournoi
    seed_number = models.PositiveIntegerField(null=True, blank=True, help_text="Tête de série")
    special_requirements = models.TextField(blank=True, verbose_name="Exigences particulières")
    
    # Statistiques dans ce tournoi
    tournament_points = models.PositiveIntegerField(default=0)
    tournament_matches_played = models.PositiveIntegerField(default=0)
    tournament_matches_won = models.PositiveIntegerField(default=0)
    tournament_matches_drawn = models.PositiveIntegerField(default=0)
    tournament_matches_lost = models.PositiveIntegerField(default=0)
    tournament_goals_for = models.PositiveIntegerField(default=0)
    tournament_goals_against = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'team_tournament_registrations'
        verbose_name = 'Inscription de tournoi'
        verbose_name_plural = 'Inscriptions de tournoi'
        unique_together = ['team', 'tournament']
        ordering = ['-registration_date']
    
    def __str__(self):
        return f"{self.team.name} - {self.tournament.name}"
    
    @property
    def tournament_goal_difference(self):
        return self.tournament_goals_for - self.tournament_goals_against


class TeamStaff(models.Model):
    """
    Staff technique d'une équipe
    """
    
    ROLE_CHOICES = (
        ('head_coach', 'Entraîneur principal'),
        ('assistant_coach', 'Entraîneur adjoint'),
        ('goalkeeper_coach', 'Entraîneur des gardiens'),
        ('physical_trainer', 'Préparateur physique'),
        ('physiotherapist', 'Kinésithérapeute'),
        ('manager', 'Manager'),
        ('doctor', 'Médecin'),
    )
    
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='staff')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    
    # Qualifications
    license_level = models.CharField(max_length=50, blank=True, verbose_name="Niveau de licence")
    experience_years = models.PositiveIntegerField(default=0, verbose_name="Années d'expérience")
    specialization = models.CharField(max_length=200, blank=True, verbose_name="Spécialisation")
    
    # Dates
    start_date = models.DateField(verbose_name="Date de début")
    end_date = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'team_staff'
        verbose_name = 'Staff d\'équipe'
        verbose_name_plural = 'Staff d\'équipe'
        unique_together = ['team', 'user', 'role']
        ordering = ['team', 'role']
    
    def __str__(self):
        return f"{self.user.name} - {self.get_role_display()} ({self.team.name})"
