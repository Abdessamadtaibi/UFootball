from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from tournaments.models import Tournament, TournamentGroup

User = get_user_model()


# ─────────────────────────────────────────────
# Sport
# ─────────────────────────────────────────────

class Sport(models.Model):
    """
    Discipline sportive (football, basket, golf, tennis, etc.)
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="Nom du sport")
    description = models.TextField(blank=True, verbose_name="Description")
    icon = models.ImageField(upload_to='sport_icons/', blank=True, null=True, verbose_name="Icône")
    club = models.ForeignKey(
        'Club',
        on_delete=models.CASCADE,
        related_name='sports',
        verbose_name='Club',
        null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sports'
        verbose_name = 'Sport'
        verbose_name_plural = 'Sports'
        ordering = ['name']

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────
# Club
# ─────────────────────────────────────────────

class Club(models.Model):
    """
    Club sportif — entité principale de l'application.
    """

    name = models.CharField(max_length=200, verbose_name="Nom du club", unique=True)
    short_name = models.CharField(max_length=10, verbose_name="Nom court", help_text="Ex: PSG, OM", unique=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_clubs',
        verbose_name='Propriétaire'
    )

    # Discipline principale du club
    discipline = models.CharField(
        max_length=100,
        default='Football',
        verbose_name="Discipline",
        help_text="Discipline principale du club (ex: Football, Basket, Golf)"
    )

    # Informations visuelles
    logo = models.ImageField(upload_to='club_logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default="#000000", help_text="Couleur principale (hex)")
    secondary_color = models.CharField(max_length=7, default="#FFFFFF", help_text="Couleur secondaire (hex)")

    # Informations de contact
    address = models.TextField(verbose_name="Adresse", blank=True)
    city = models.CharField(max_length=100, blank=True, verbose_name="Ville")
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    # Informations administratives
    license_number = models.CharField(max_length=50, blank=True, verbose_name="Numéro de licence")
    founded_year = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1800), MaxValueValidator(2030)]
    )

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


# ─────────────────────────────────────────────
# Season
# ─────────────────────────────────────────────

class Season(models.Model):
    """
    Saison sportive d'un club (ex: 2025-2026).
    is_active s'active/désactive automatiquement selon les dates.
    """
    name = models.CharField(max_length=100, verbose_name="Nom de la saison")  # "2025-2026"
    team = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='seasons', verbose_name="Équipe", null=True, blank=True)
    start_date = models.DateField(verbose_name="Date de début")
    end_date = models.DateField(verbose_name="Date de fin")
    is_active = models.BooleanField(default=False, verbose_name="Saison active")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seasons'
        verbose_name = 'Saison'
        verbose_name_plural = 'Saisons'
        ordering = ['-start_date']
        unique_together = ['team', 'name']

    def __str__(self):
        return f"{self.team.name if self.team else 'Sans équipe'} – {self.name}"

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("La date de début doit être antérieure à la date de fin.")

    def save(self, *args, **kwargs):
        """Auto-set is_active based on today's date."""
        from datetime import date
        today = date.today()
        if self.start_date and self.end_date:
            self.is_active = self.start_date <= today <= self.end_date
        super().save(*args, **kwargs)

    def refresh_status(self):
        """Re-check is_active and save if changed."""
        from datetime import date
        today = date.today()
        new_active = self.start_date <= today <= self.end_date
        if new_active != self.is_active:
            self.is_active = new_active
            self.save(update_fields=['is_active', 'updated_at'])


# ─────────────────────────────────────────────
# Category
# ─────────────────────────────────────────────

class Category(models.Model):
    """
    Catégorie d'âge d'un club (U6, U8, U10, U13, …)
    Configurable par club pour s'adapter à toutes les disciplines.
    """
    name = models.CharField(max_length=20, verbose_name="Nom de la catégorie")  # e.g. U13
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='categories', verbose_name="Club")
    description = models.CharField(max_length=200, blank=True, verbose_name="Description")
    min_age = models.PositiveIntegerField(null=True, blank=True, verbose_name="Âge minimum")
    max_age = models.PositiveIntegerField(null=True, blank=True, verbose_name="Âge maximum")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        verbose_name = 'Catégorie'
        verbose_name_plural = 'Catégories'
        ordering = ['club', 'order', 'name']
        unique_together = ['club', 'name']

    def __str__(self):
        return f"{self.club.short_name} – {self.name}"


# ─────────────────────────────────────────────
# Team
# ─────────────────────────────────────────────

class Team(models.Model):

    CATEGORY_CHOICES = (
        ('u6', 'U6'),
        ('u7', 'U7'),
        ('u8', 'U8'),
        ('u9', 'U9'),
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
        ('u21', 'U21'),
        ('senior', 'Senior'),
        ('veteran', 'Vétéran'),
    )

    SPORT_CHOICES = (
        ('football', 'Football'),
        ('basketball', 'Basketball'),
        ('handball', 'Handball'),
        ('volleyball', 'Volleyball'),
        ('rugby', 'Rugby'),
        ('tennis', 'Tennis'),
        ('golf', 'Golf'),
        ('swimming', 'Natation'),
        ('athletics', 'Athlétisme'),
        ('other', 'Autre'),
    )

    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=200, verbose_name="Nom de l'équipe")
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default='u13')

    # Sport de l'équipe (choix simple)
    sport = models.CharField(
        max_length=20,
        choices=SPORT_CHOICES,
        default='football',
        verbose_name="Sport"
    )

    # Lien vers la catégorie dynamique (optionnel — complète le champ texte)
    category_obj = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teams',
        verbose_name="Catégorie (objet)"
    )

    # Saison associée
    season = models.ForeignKey(
        Season,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teams',
        verbose_name="Saison"
    )

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

    # Terrain par défaut
    default_venue = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Terrain par défaut",
        help_text="Nom du terrain où l'équipe joue habituellement"
    )

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


# ─────────────────────────────────────────────
# Player
# ─────────────────────────────────────────────

class Player(models.Model):
    """
    Fiche joueur complète. Conforme au cahier des charges.
    """

    POSITION_CHOICES = [
        ('GB', 'Gardien de but'),
        ('DG', 'Arrière gauche'),
        ('DC', 'Défenseur central'),
        ('DD', 'Arrière droit'),
        ('MDC', 'Milieu défensif central'),
        ('MC', 'Milieu central'),
        ('MD', 'Milieu droit'),
        ('MG', 'Milieu gauche'),
        ('AD', 'Ailier droit'),
        ('AG', 'Ailier gauche'),
        ('AC', 'Avant-centre'),
        ('ATT', 'Attaquant'),
    ]

    STATUS_CHOICES = [
        ('actif', 'Actif'),
        ('suspendu', 'Suspendu'),
        ('sorti', 'Sorti'),
    ]

    BLOOD_TYPE_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    # ── Identité ──────────────────────────────
    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    birth_date = models.DateField(verbose_name="Date de naissance")
    birth_place = models.CharField(max_length=200, blank=True, verbose_name="Lieu de naissance")
    nationality = models.CharField(max_length=100, blank=True, verbose_name="Nationalité", default="Marocaine")
    photo = models.ImageField(upload_to='player_photos/', blank=True, null=True, verbose_name="Photo")

    # ── Coordonnées ───────────────────────────
    address = models.TextField(blank=True, verbose_name="Adresse")
    city = models.CharField(max_length=100, blank=True, verbose_name="Ville")

    # ── Responsables légaux ───────────────────
    # Père
    father_name = models.CharField(max_length=200, blank=True, verbose_name="Nom complet du père")
    father_phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone du père")
    father_email = models.EmailField(blank=True, verbose_name="Email du père")

    # Mère
    mother_name = models.CharField(max_length=200, blank=True, verbose_name="Nom complet de la mère")
    mother_phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone de la mère")
    mother_email = models.EmailField(blank=True, verbose_name="Email de la mère")

    # ── Informations médicales ────────────────
    blood_type = models.CharField(
        max_length=3, choices=BLOOD_TYPE_CHOICES, blank=True, verbose_name="Groupe sanguin"
    )
    allergies = models.TextField(blank=True, verbose_name="Allergies / remarques médicales")
    medical_authorization = models.BooleanField(
        default=False, verbose_name="Autorisation médicale"
    )
    treating_doctor = models.CharField(max_length=200, blank=True, verbose_name="Médecin traitant")

    # ── Informations physiques ────────────────
    height = models.PositiveIntegerField(null=True, blank=True, help_text="Taille en cm")
    weight = models.PositiveIntegerField(null=True, blank=True, help_text="Poids en kg")

    # ── Autorisations ─────────────────────────
    parental_authorization = models.BooleanField(default=False, verbose_name="Autorisation parentale")
    transport_authorization = models.BooleanField(default=False, verbose_name="Autorisation de transport")
    image_authorization = models.BooleanField(default=False, verbose_name="Autorisation d'utilisation d'image")
    digital_signature = models.ImageField(
        upload_to='signatures/', blank=True, null=True, verbose_name="Signature digitale du parent"
    )

    # ── Informations sportives ────────────────
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='players')
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='players',
        verbose_name="Catégorie"
    )
    jersey_number = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(99)])
    position = models.CharField(max_length=3, choices=POSITION_CHOICES, blank=True)
    is_captain = models.BooleanField(default=False, verbose_name="Capitaine")
    is_main_player = models.BooleanField(
        default=False,
        verbose_name="Joueur titulaire",
        help_text="Fait partie des 11 joueurs principaux de l'équipe"
    )
    enrollment_date = models.DateField(null=True, blank=True, verbose_name="Date d'inscription")
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='actif', verbose_name="Statut"
    )

    # ── Statistiques ──────────────────────────
    goals_scored = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)
    yellow_cards = models.PositiveIntegerField(default=0)
    red_cards = models.PositiveIntegerField(default=0)
    minutes_played = models.PositiveIntegerField(default=0)

    # ── Métadonnées ───────────────────────────
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
            main_players_count = Player.objects.filter(
                team=self.team,
                is_main_player=True,
                is_active=True
            ).exclude(pk=self.pk).count()
            if main_players_count >= 11:
                raise ValidationError({
                    'is_main_player': "Cette équipe a déjà 11 joueurs titulaires. Vous devez d'abord retirer un joueur titulaire."
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        from datetime import date
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )


# ─────────────────────────────────────────────
# Coach
# ─────────────────────────────────────────────

class Coach(models.Model):
    """
    Fiche coach — profil personnel distinct de TeamStaff (qui gère les affectations).
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='coach_profile',
        verbose_name="Utilisateur associé"
    )
    team = models.ForeignKey('Team', on_delete=models.CASCADE, related_name='coaches', verbose_name="Équipe", null=True, blank=True)

    # Identité
    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    birth_date = models.DateField(null=True, blank=True, verbose_name="Date de naissance")
    nationality = models.CharField(max_length=100, blank=True, verbose_name="Nationalité")
    photo = models.ImageField(upload_to='coach_photos/', blank=True, null=True, verbose_name="Photo")

    # Contact
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    email = models.EmailField(verbose_name="Email")
    address = models.TextField(blank=True, verbose_name="Adresse")

    # Qualifications
    diplomas = models.TextField(blank=True, verbose_name="Diplômes")
    certifications = models.TextField(blank=True, verbose_name="Certifications")
    license_level = models.CharField(max_length=50, blank=True, verbose_name="Niveau de licence")
    experience_years = models.PositiveIntegerField(default=0, verbose_name="Années d'expérience")
    specialization = models.CharField(max_length=200, blank=True, verbose_name="Spécialisation")

    # Catégories encadrées
    supervised_categories = models.ManyToManyField(
        Category, blank=True, related_name='coaches', verbose_name="Catégories encadrées"
    )

    # Disponibilités (texte libre ou JSON)
    availabilities = models.TextField(blank=True, verbose_name="Disponibilités")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coaches'
        verbose_name = 'Coach'
        verbose_name_plural = 'Coachs'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.team.name if self.team else 'Sans équipe'})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


# ─────────────────────────────────────────────
# TeamTournamentRegistration
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# TeamStaff
# ─────────────────────────────────────────────

class TeamStaff(models.Model):
    """
    Staff technique affecté à une équipe (affectation/rôle).
    Distinct du modèle Coach qui gère le profil personnel du coach.
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
        verbose_name = "Staff d'équipe"
        verbose_name_plural = "Staff d'équipe"
        unique_together = ['team', 'user', 'role']
        ordering = ['team', 'role']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_role_display()} ({self.team.name})"


# ─────────────────────────────────────────────
# SeasonTeamStats
# ─────────────────────────────────────────────

class SeasonTeamStats(models.Model):
    """
    Statistiques agrégées d'une équipe pour une saison.
    Mises à jour automatiquement lorsqu'un match est terminé.
    """
    season = models.OneToOneField(Season, on_delete=models.CASCADE, related_name='team_stats')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='season_stats')

    # Résultats
    matches_played = models.PositiveIntegerField(default=0)
    matches_won = models.PositiveIntegerField(default=0)
    matches_drawn = models.PositiveIntegerField(default=0)
    matches_lost = models.PositiveIntegerField(default=0)
    goals_for = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)
    clean_sheets = models.PositiveIntegerField(default=0, verbose_name="Clean sheets")

    # Discipline
    yellow_cards = models.PositiveIntegerField(default=0)
    red_cards = models.PositiveIntegerField(default=0)

    # Trophées et classement
    trophies_won = models.PositiveIntegerField(default=0)
    best_finish = models.CharField(max_length=100, blank=True, verbose_name="Meilleur résultat")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'season_team_stats'
        verbose_name = "Statistiques d'équipe (saison)"
        verbose_name_plural = "Statistiques d'équipe (saisons)"

    def __str__(self):
        return f"{self.team.name} – {self.season.name}"

    @property
    def goal_difference(self):
        return self.goals_for - self.goals_against

    @property
    def points(self):
        return (self.matches_won * 3) + self.matches_drawn

    @property
    def win_rate(self):
        if self.matches_played == 0:
            return 0
        return round((self.matches_won / self.matches_played) * 100, 1)


# ─────────────────────────────────────────────
# SeasonPlayerStats
# ─────────────────────────────────────────────

class SeasonPlayerStats(models.Model):
    """
    Statistiques individuelles d'un joueur pour une saison.
    Mises à jour automatiquement à partir des MatchLineup.
    """
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='player_stats')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='season_stats')

    # Participation
    matches_played = models.PositiveIntegerField(default=0)
    matches_started = models.PositiveIntegerField(default=0)
    minutes_played = models.PositiveIntegerField(default=0)

    # Offensive
    goals_scored = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)

    # Discipline
    yellow_cards = models.PositiveIntegerField(default=0)
    red_cards = models.PositiveIntegerField(default=0)

    # Évaluation
    average_rating = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True,
        verbose_name="Note moyenne"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'season_player_stats'
        verbose_name = 'Statistiques joueur (saison)'
        verbose_name_plural = 'Statistiques joueurs (saison)'
        unique_together = ['season', 'player']
        ordering = ['-goals_scored', '-assists']

    def __str__(self):
        return f"{self.player.full_name} – {self.season.name}"


# ─────────────────────────────────────────────
# SeasonPlayerRoster
# ─────────────────────────────────────────────

class SeasonPlayerRoster(models.Model):
    """
    Snapshot de l'effectif d'une équipe au moment de la saison.
    Préserve les données même si le joueur change d'équipe ou de poste.
    """
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='player_roster')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='season_rosters')

    # Frozen copy of player identity at snapshot time
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    birth_date = models.DateField()
    jersey_number = models.PositiveIntegerField()
    position = models.CharField(max_length=3, blank=True)
    is_captain = models.BooleanField(default=False)
    is_main_player = models.BooleanField(default=False)
    status = models.CharField(max_length=10, default='actif')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'season_player_roster'
        verbose_name = 'Effectif saison'
        verbose_name_plural = 'Effectifs saison'
        unique_together = ['season', 'player']
        ordering = ['jersey_number']

    def __str__(self):
        return f"{self.first_name} {self.last_name} (#{self.jersey_number}) – {self.season.name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


# ─────────────────────────────────────────────
# SeasonTournamentResult
# ─────────────────────────────────────────────

class SeasonTournamentResult(models.Model):
    """
    Résultat d'une équipe dans un tournoi au cours d'une saison.
    """
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='tournament_results')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='season_tournament_results')
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='season_results')

    # Classement
    final_position = models.PositiveIntegerField(null=True, blank=True, verbose_name="Position finale")
    group_name = models.CharField(max_length=50, blank=True, verbose_name="Nom du groupe")
    group_position = models.PositiveIntegerField(null=True, blank=True, verbose_name="Position dans le groupe")

    # Statistiques dans ce tournoi
    points = models.PositiveIntegerField(default=0)
    matches_played = models.PositiveIntegerField(default=0)
    matches_won = models.PositiveIntegerField(default=0)
    matches_drawn = models.PositiveIntegerField(default=0)
    matches_lost = models.PositiveIntegerField(default=0)
    goals_for = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)

    # Distinction
    is_champion = models.BooleanField(default=False, verbose_name="Champion")
    trophy_name = models.CharField(max_length=100, blank=True, verbose_name="Trophée",
                                   help_text="Ex: Vainqueur, Meilleure défense, Fair-play")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'season_tournament_results'
        verbose_name = 'Résultat tournoi (saison)'
        verbose_name_plural = 'Résultats tournois (saison)'
        unique_together = ['season', 'team', 'tournament']
        ordering = ['final_position']

    def __str__(self):
        pos = f"#{self.final_position}" if self.final_position else "?"
        return f"{self.team.name} – {self.tournament.name} ({pos})"

    @property
    def goal_difference(self):
        return self.goals_for - self.goals_against
