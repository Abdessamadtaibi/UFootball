from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from tournaments.models import Tournament, TournamentPhase, TournamentGroup
from teams.models import Team, Player
import uuid

User = get_user_model()


class Match(models.Model):
    """
    Modèle pour les matchs U13
    """
    
    STATUS_CHOICES = (
        ('scheduled', 'Programmé'),
        ('live', 'En cours'),
        ('half_time', 'Mi-temps'),
        ('finished', 'Terminé'),
        ('postponed', 'Reporté'),
        ('cancelled', 'Annulé'),
    )
    
    MATCH_TYPE_CHOICES = (
        ('group_stage', 'Phase de groupes'),
        ('knockout', 'Élimination directe'),
        ('friendly', 'Match amical'),
        ('final', 'Finale'),
        ('semi_final', 'Demi-finale'),
        ('quarter_final', 'Quart de finale'),
        ('third_place', 'Match pour la 3ème place'),
    )
    
    # Informations de base
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='matches', null=True, blank=True)
    phase = models.ForeignKey(TournamentPhase, on_delete=models.SET_NULL, null=True, blank=True)
    group = models.ForeignKey(TournamentGroup, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Équipes
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches')
    
    # Date et heure
    scheduled_date = models.DateTimeField(verbose_name="Date et heure prévues")
    actual_start_time = models.DateTimeField(null=True, blank=True, verbose_name="Heure de début réelle")
    actual_end_time = models.DateTimeField(null=True, blank=True, verbose_name="Heure de fin réelle")
    
    # Lieu
    venue_name = models.CharField(max_length=200, verbose_name="Nom du terrain")
    venue_address = models.TextField(blank=True, verbose_name="Adresse du terrain")
    field_number = models.CharField(max_length=10, blank=True, verbose_name="Numéro de terrain")
    
    # Statut et type
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='scheduled')
    match_type = models.CharField(max_length=15, choices=MATCH_TYPE_CHOICES, default='group_stage')
    
    # Scores
    home_score = models.PositiveIntegerField(default=0)
    away_score = models.PositiveIntegerField(default=0)
    home_score_half_time = models.PositiveIntegerField(default=0)
    away_score_half_time = models.PositiveIntegerField(default=0)
    
    # Prolongations et tirs au but (pour les phases finales)
    home_score_extra_time = models.PositiveIntegerField(null=True, blank=True)
    away_score_extra_time = models.PositiveIntegerField(null=True, blank=True)
    home_score_penalties = models.PositiveIntegerField(null=True, blank=True)
    away_score_penalties = models.PositiveIntegerField(null=True, blank=True)
    
    # Arbitrage
    referee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='refereed_matches')
    assistant_referee_1 = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assisted_matches_1')
    assistant_referee_2 = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assisted_matches_2')
    
    # Informations supplémentaires
    weather_conditions = models.CharField(max_length=100, blank=True, verbose_name="Conditions météo")
    attendance = models.PositiveIntegerField(null=True, blank=True, verbose_name="Nombre de spectateurs")
    notes = models.TextField(blank=True, verbose_name="Notes du match")
    
    # Match number/round (like tournaments model)
    round_number = models.PositiveIntegerField(default=1, help_text="Journée/Tour")
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_matches')
    last_updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_matches')
    
    class Meta:
        db_table = 'matches'
        verbose_name = 'Match'
        verbose_name_plural = 'Matchs'
        ordering = ['-scheduled_date']
    
    def __str__(self):
        return f"{self.home_team.name} vs {self.away_team.name} - {self.scheduled_date.strftime('%d/%m/%Y %H:%M')}"
    
    @property
    def winner(self):
        """Retourne l'équipe gagnante ou None en cas de match nul"""
        if self.status != 'finished':
            return None
        
        # Vérifier les tirs au but d'abord
        if self.home_score_penalties is not None and self.away_score_penalties is not None:
            if self.home_score_penalties > self.away_score_penalties:
                return self.home_team
            elif self.away_score_penalties > self.home_score_penalties:
                return self.away_team
        
        # Vérifier les prolongations
        if self.home_score_extra_time is not None and self.away_score_extra_time is not None:
            if self.home_score_extra_time > self.away_score_extra_time:
                return self.home_team
            elif self.away_score_extra_time > self.home_score_extra_time:
                return self.away_team
        
        # Score normal
        if self.home_score > self.away_score:
            return self.home_team
        elif self.away_score > self.home_score:
            return self.away_team
        
        return None  # Match nul
    
    @property
    def is_draw(self):
        """Vérifie si le match est un match nul"""
        return self.winner is None and self.status == 'finished'
    
    @property
    def duration_minutes(self):
        """Calcule la durée du match en minutes"""
        if self.actual_start_time and self.actual_end_time:
            duration = self.actual_end_time - self.actual_start_time
            return int(duration.total_seconds() / 60)
        return None


class MatchEvent(models.Model):
    """
    Événements d'un match (buts, cartons, etc.)
    """
    
    EVENT_TYPE_CHOICES = (
        ('goal', 'But'),
        ('own_goal', 'But contre son camp'),
        ('penalty_goal', 'But sur penalty'),
        ('yellow_card', 'Carton jaune'),
        ('red_card', 'Carton rouge'),
        ('substitution', 'Remplacement'),
        ('injury', 'Blessure'),
        ('timeout', 'Temps mort'),
    )
    
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='events')
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    
    event_type = models.CharField(max_length=15, choices=EVENT_TYPE_CHOICES)
    minute = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(120)])
    additional_time = models.PositiveIntegerField(default=0, verbose_name="Temps additionnel")
    
    # Pour les remplacements
    substituted_player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True, blank=True, related_name='substituted_events')
    
    # Pour les buts avec assistance
    assist_player = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='assist_events')
    
    description = models.TextField(blank=True, verbose_name="Description de l'événement")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'match_events'
        verbose_name = 'Événement de match'
        verbose_name_plural = 'Événements de match'
        ordering = ['minute', 'additional_time', 'created_at']
    
    def __str__(self):
        time_str = f"{self.minute}'"
        if self.additional_time > 0:
            time_str += f"+{self.additional_time}"
        return f"{self.get_event_type_display()} - {self.player.full_name} ({time_str})"


class MatchLineup(models.Model):
    """
    Composition d'équipe pour un match
    """
    
    POSITION_CHOICES = (
        ('GK', 'Gardien'),
        ('RB', 'Arrière droit'),
        ('CB', 'Défenseur central'),
        ('LB', 'Arrière gauche'),
        ('CDM', 'Milieu défensif'),
        ('CM', 'Milieu central'),
        ('CAM', 'Milieu offensif'),
        ('RW', 'Ailier droit'),
        ('LW', 'Ailier gauche'),
        ('ST', 'Attaquant'),
        ('SUB', 'Remplaçant'),
    )
    
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='lineups')
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    
    position = models.CharField(max_length=3, choices=POSITION_CHOICES)
    is_starter = models.BooleanField(default=True, verbose_name="Titulaire")
    is_captain = models.BooleanField(default=False, verbose_name="Capitaine")
    
    # Statistiques du joueur dans ce match
    minutes_played = models.PositiveIntegerField(default=0)
    goals_scored = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)
    yellow_cards = models.PositiveIntegerField(default=0)
    red_cards = models.PositiveIntegerField(default=0)
    
    # Évaluation (optionnel)
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, 
                                validators=[MinValueValidator(0), MaxValueValidator(10)])
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'match_lineups'
        verbose_name = 'Composition de match'
        verbose_name_plural = 'Compositions de match'
        unique_together = ['match', 'team', 'player']
        ordering = ['is_starter', 'position']
    
    def __str__(self):
        starter_status = "Titulaire" if self.is_starter else "Remplaçant"
        return f"{self.player.full_name} - {self.get_position_display()} ({starter_status})"


class MatchStatistics(models.Model):
    """
    Statistiques détaillées d'un match par équipe
    """
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='statistics')
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    
    # Statistiques de possession et jeu
    possession_percentage = models.PositiveIntegerField(default=50, validators=[MinValueValidator(0), MaxValueValidator(100)])
    shots_total = models.PositiveIntegerField(default=0)
    shots_on_target = models.PositiveIntegerField(default=0)
    shots_off_target = models.PositiveIntegerField(default=0)
    shots_blocked = models.PositiveIntegerField(default=0)
    
    # Passes
    passes_total = models.PositiveIntegerField(default=0)
    passes_completed = models.PositiveIntegerField(default=0)
    pass_accuracy = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Actions défensives
    tackles_total = models.PositiveIntegerField(default=0)
    tackles_won = models.PositiveIntegerField(default=0)
    interceptions = models.PositiveIntegerField(default=0)
    clearances = models.PositiveIntegerField(default=0)
    
    # Fautes et cartons
    fouls_committed = models.PositiveIntegerField(default=0)
    fouls_suffered = models.PositiveIntegerField(default=0)
    yellow_cards = models.PositiveIntegerField(default=0)
    red_cards = models.PositiveIntegerField(default=0)
    
    # Corners et coups francs
    corners = models.PositiveIntegerField(default=0)
    free_kicks = models.PositiveIntegerField(default=0)
    offsides = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'match_statistics'
        verbose_name = 'Statistiques de match'
        verbose_name_plural = 'Statistiques de match'
        unique_together = ['match', 'team']
    
    def __str__(self):
        return f"Stats {self.team.name} vs {self.match}"


class MatchReport(models.Model):
    """
    Rapport de match rédigé par les arbitres ou organisateurs
    """
    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name='report')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Contenu du rapport
    summary = models.TextField(verbose_name="Résumé du match")
    key_moments = models.TextField(blank=True, verbose_name="Moments clés")
    referee_notes = models.TextField(blank=True, verbose_name="Notes de l'arbitre")
    
    # Évaluations
    home_team_performance = models.TextField(blank=True, verbose_name="Performance équipe domicile")
    away_team_performance = models.TextField(blank=True, verbose_name="Performance équipe extérieure")
    
    # Incidents
    incidents = models.TextField(blank=True, verbose_name="Incidents particuliers")
    disciplinary_actions = models.TextField(blank=True, verbose_name="Actions disciplinaires")
    
    # Conditions de jeu
    field_conditions = models.CharField(max_length=100, blank=True, verbose_name="État du terrain")
    weather_impact = models.TextField(blank=True, verbose_name="Impact météorologique")
    
    # Validation
    is_validated = models.BooleanField(default=False, verbose_name="Rapport validé")
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='validated_reports')
    validated_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'match_reports'
        verbose_name = 'Rapport de match'
        verbose_name_plural = 'Rapports de match'
    
    def __str__(self):
        return f"Rapport - {self.match}"
