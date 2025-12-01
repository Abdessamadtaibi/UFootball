from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
import uuid

User = get_user_model()


class Tournament(models.Model):
    """
    Modèle pour les tournois U13
    """
    
    STATUS_CHOICES = (
        ('upcoming', 'À venir'),
        ('active', 'En cours'),
        ('finished', 'Terminé'),
        ('cancelled', 'Annulé'),
    )
    
    # UPDATED: New tournament types
    TYPE_CHOICES = (
        ('league', 'Championnat (Type Ligue)'),  # Like La Liga - single table
        ('group_knockout', 'Groupes + Élimination'),  # Like Champions League
    )
    
    FORMAT_CHOICES = (
        ('round_robin', 'Round Robin'),
        ('knockout', 'Élimination directe'),
        ('group_knockout', 'Phase de groupes + Élimination'),
        ('league', 'Championnat'),
    )
    
    # Informations de base
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name="Nom du tournoi")
    description = models.TextField(blank=True, verbose_name="Description")
    
    # NEW: Tournament type
    tournament_type = models.CharField(
        max_length=20, 
        choices=TYPE_CHOICES, 
        default='league',
        verbose_name="Type de tournoi"
    )
    
    # Dates et lieu
    start_date = models.DateField(verbose_name="Date de début")
    end_date = models.DateField(verbose_name="Date de fin")
    location = models.CharField(max_length=200, verbose_name="Lieu")
    venue_address = models.TextField(blank=True, verbose_name="Adresse complète")
    
    # Configuration du tournoi
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='upcoming')
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default='group_knockout')
    max_teams = models.PositiveIntegerField(default=16, validators=[MinValueValidator(4), MaxValueValidator(64)])
    
    # NEW: Only for group_knockout type
    number_of_groups = models.PositiveIntegerField(
        default=4, 
        validators=[MinValueValidator(1), MaxValueValidator(16)],
        help_text="Seulement pour les tournois avec groupes"
    )
    teams_qualify_per_group = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        help_text="Nombre d'équipes qualifiées par groupe"
    )
    
    # Organisateurs
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organized_tournaments')
    staff_members = models.ManyToManyField(User, blank=True, related_name='staff_tournaments')
    
    # Médias
    logo = models.ImageField(upload_to='tournament_logos/', blank=True, null=True)
    banner_image = models.ImageField(upload_to='tournament_banners/', blank=True, null=True)
    
    # Règles et informations
    rules = models.TextField(blank=True, verbose_name="Règlement")
    prize_description = models.TextField(blank=True, verbose_name="Prix et récompenses")
    registration_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    
    # Paramètres de match
    match_duration = models.PositiveIntegerField(default=60, help_text="Durée en minutes")
    half_time_duration = models.PositiveIntegerField(default=10, help_text="Mi-temps en minutes")
    
    # NEW: Scoring rules
    points_per_win = models.PositiveIntegerField(default=3)
    points_per_draw = models.PositiveIntegerField(default=1)
    points_per_loss = models.PositiveIntegerField(default=0)
    
    # Métadonnées
    is_public = models.BooleanField(default=True, verbose_name="Tournoi public")
    registration_open = models.BooleanField(default=True, verbose_name="Inscriptions ouvertes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tournaments'
        verbose_name = 'Tournoi'
        verbose_name_plural = 'Tournois'
        ordering = ['-start_date']
    
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
    
    def clean(self):
        """Validate tournament configuration"""
        if self.tournament_type == 'league' and self.number_of_groups > 1:
            raise ValidationError({
                'number_of_groups': 'Un tournoi de type championnat ne peut avoir qu\'un seul groupe'
            })
    
    @property
    def registered_teams_count(self):
        from django.apps import apps
        TeamGroup = apps.get_model('tournaments', 'TeamGroup')
        # Count unique teams across all groups in this tournament
        unique_teams = TeamGroup.objects.filter(group__tournament=self).values('team').distinct().count()
        # Also count teams directly registered through TeamTournamentRegistration
        from teams.models import TeamTournamentRegistration
        registered_teams = TeamTournamentRegistration.objects.filter(tournament=self, status='confirmed').count()
        # Return the maximum of both counts to ensure accuracy
        return max(unique_teams, registered_teams)
    
    @property
    def is_full(self):
        return self.registered_teams_count >= self.max_teams
    
    @property
    def can_register(self):
        return self.registration_open and not self.is_full and self.status == 'upcoming'


class TournamentGroup(models.Model):
    """
    Groupes dans un tournoi (pour les phases de groupes)
    Pour Type 1 (League): Un seul groupe contenant toutes les équipes
    Pour Type 2 (Group+Knockout): Plusieurs groupes
    """
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=50, verbose_name="Nom du groupe")  # Ex: "Groupe A" ou "Ligue"
    description = models.TextField(blank=True)
    
    # NEW: Group order for knockout phase
    order = models.PositiveIntegerField(default=1)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tournament_groups'
        verbose_name = 'Groupe de tournoi'
        verbose_name_plural = 'Groupes de tournoi'
        unique_together = ['tournament', 'name']
        ordering = ['order', 'name']
    
    def __str__(self):
        return f"{self.tournament.name} - {self.name}"
    
    def get_standings(self):
        """
        Calculate group standings based on matches
        Returns teams ordered by: points, goal_difference, goals_scored
        """
        from django.db.models import Count, Q, Sum, F
        
        standings = []
        teams = self.team_groups.select_related('team__club').all()
        
        for team_group in teams:
            team = team_group.team
            # Get matches where team participated in this group
            # Use tournament-specific reverse relations to avoid clashes
            home_matches = team.tournament_home_matches.filter(group=self, status='finished')
            away_matches = team.tournament_away_matches.filter(group=self, status='finished')
            
            wins = home_matches.filter(home_score__gt=F('away_score')).count() + \
                   away_matches.filter(away_score__gt=F('home_score')).count()
            
            draws = home_matches.filter(home_score=F('away_score')).count() + \
                    away_matches.filter(home_score=F('away_score')).count()
            
            losses = home_matches.filter(home_score__lt=F('away_score')).count() + \
                     away_matches.filter(away_score__lt=F('home_score')).count()
            
            goals_scored = (home_matches.aggregate(total=Sum('home_score'))['total'] or 0) + \
                          (away_matches.aggregate(total=Sum('away_score'))['total'] or 0)
            
            goals_conceded = (home_matches.aggregate(total=Sum('away_score'))['total'] or 0) + \
                            (away_matches.aggregate(total=Sum('home_score'))['total'] or 0)
            
            points = (wins * self.tournament.points_per_win + 
                     draws * self.tournament.points_per_draw + 
                     losses * self.tournament.points_per_loss)
            
            standings.append({
                'team': team,
                'team_group': team_group,
                'played': wins + draws + losses,
                'wins': wins,
                'draws': draws,
                'losses': losses,
                'goals_scored': goals_scored,
                'goals_conceded': goals_conceded,
                'goal_difference': goals_scored - goals_conceded,
                'points': points
            })
        
        # Sort by points, then goal difference, then goals scored
        standings.sort(key=lambda x: (-x['points'], -x['goal_difference'], -x['goals_scored']))
        
        # Add position
        for idx, standing in enumerate(standings, 1):
            standing['position'] = idx
        
        return standings


class TournamentPhase(models.Model):
    """
    Phases d'un tournoi (Phase de groupes, Quarts de finale, etc.)
    """
    
    PHASE_TYPES = (
        ('group_stage', 'Phase de groupes'),
        ('round_16', 'Huitièmes de finale'),
        ('quarter_final', 'Quarts de finale'),
        ('semi_final', 'Demi-finales'),
        ('final', 'Finale'),
        ('third_place', 'Match pour la 3ème place'),
    )
    
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='phases')
    name = models.CharField(max_length=50)
    phase_type = models.CharField(max_length=20, choices=PHASE_TYPES)
    order = models.PositiveIntegerField(default=1)
    
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tournament_phases'
        verbose_name = 'Phase de tournoi'
        verbose_name_plural = 'Phases de tournoi'
        ordering = ['order']
        unique_together = ['tournament', 'phase_type']
    
    def __str__(self):
        return f"{self.tournament.name} - {self.name}"


# NEW MODEL: Team participation in groups
class TeamGroup(models.Model):
    """
    Association between teams and tournament groups
    Tracks which teams are in which groups
    """
    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='tournament_groups')
    group = models.ForeignKey(TournamentGroup, on_delete=models.CASCADE, related_name='team_groups')
    
    # Position in group (for display ordering)
    position = models.PositiveIntegerField(null=True, blank=True)
    
    # Qualification status (for knockout phases)
    is_qualified = models.BooleanField(default=False)
    qualified_position = models.PositiveIntegerField(null=True, blank=True)
    
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'team_groups'
        verbose_name = 'Équipe dans groupe'
        verbose_name_plural = 'Équipes dans groupes'
        unique_together = ['team', 'group']
        ordering = ['position', 'team__name']
    
    def __str__(self):
        return f"{self.team.name} - {self.group.name}"


# NEW MODEL: Matches
class Match(models.Model):
    """
    Matches within tournaments
    """
    STATUS_CHOICES = (
        ('scheduled', 'Programmé'),
        ('live', 'En cours'),
        ('finished', 'Terminé'),
        ('postponed', 'Reporté'),
        ('cancelled', 'Annulé'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Tournament and phase/group
    # Use distinct related_name to avoid clash with matches app
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='tournament_matches')
    group = models.ForeignKey(TournamentGroup, on_delete=models.CASCADE, null=True, blank=True, related_name='matches')
    phase = models.ForeignKey(TournamentPhase, on_delete=models.CASCADE, null=True, blank=True, related_name='matches')
    
    # Teams
    # Distinct reverse names to avoid clash with matches app
    home_team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='tournament_home_matches')
    away_team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='tournament_away_matches')
    
    # Match details
    match_date = models.DateTimeField(verbose_name="Date du match")
    venue = models.CharField(max_length=200, blank=True)
    
    # Scores
    home_score = models.PositiveIntegerField(default=0)
    away_score = models.PositiveIntegerField(default=0)
    
    # Match status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    # Match number/round
    match_number = models.PositiveIntegerField(null=True, blank=True)
    round_number = models.PositiveIntegerField(default=1, help_text="Journée/Tour")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        # Use dedicated table name to avoid db_table conflict
        db_table = 'tournament_matches'
        verbose_name = 'Match'
        verbose_name_plural = 'Matches'
        ordering = ['match_date', 'match_number']
    
    def __str__(self):
        return f"{self.home_team.name} vs {self.away_team.name} - {self.match_date.strftime('%d/%m/%Y')}"
    
    def clean(self):
        """Validate match"""
        if self.home_team == self.away_team:
            raise ValidationError("Une équipe ne peut pas jouer contre elle-même")
        
        # Ensure both teams are in the same group if group is specified
        if self.group:
            home_in_group = TeamGroup.objects.filter(team=self.home_team, group=self.group).exists()
            away_in_group = TeamGroup.objects.filter(team=self.away_team, group=self.group).exists()
            
            if not (home_in_group and away_in_group):
                raise ValidationError("Les deux équipes doivent être dans le même groupe")
    
    @property
    def winner(self):
        """Return the winning team or None for draw"""
        if self.status != 'finished':
            return None
        if self.home_score > self.away_score:
            return self.home_team
        elif self.away_score > self.home_score:
            return self.away_team
        return None  # Draw


class TournamentNews(models.Model):
    """
    Actualités et annonces liées à un tournoi
    """
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='news')
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    
    is_important = models.BooleanField(default=False, verbose_name="Annonce importante")
    is_published = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tournament_news'
        verbose_name = 'Actualité de tournoi'
        verbose_name_plural = 'Actualités de tournoi'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.tournament.name} - {self.title}"