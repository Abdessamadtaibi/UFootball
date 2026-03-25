from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class TrainingSession(models.Model):
    """
    Séance d'entraînement planifiée pour une équipe.
    """

    RECURRENCE_CHOICES = [
        ('none', 'Aucune'),
        ('weekly', 'Hebdomadaire'),
        ('biweekly', 'Bi-hebdomadaire'),
    ]

    # Relations
    team = models.ForeignKey(
        'teams.Team', on_delete=models.CASCADE,
        related_name='training_sessions', verbose_name="Équipe"
    )
    category = models.ForeignKey(
        'teams.Category', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='training_sessions', verbose_name="Catégorie"
    )
    coach = models.ForeignKey(
        'teams.Coach', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='training_sessions', verbose_name="Coach responsable"
    )
    season = models.ForeignKey(
        'teams.Season', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='training_sessions', verbose_name="Saison"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_training_sessions'
    )

    # Planification
    date = models.DateField(verbose_name="Date")
    start_time = models.TimeField(verbose_name="Heure de début")
    end_time = models.TimeField(verbose_name="Heure de fin")
    location = models.CharField(max_length=200, verbose_name="Lieu")

    # Informations
    title = models.CharField(max_length=200, blank=True, verbose_name="Titre / thème")
    notes = models.TextField(blank=True, verbose_name="Notes")
    is_cancelled = models.BooleanField(default=False, verbose_name="Annulé")
    cancellation_reason = models.TextField(blank=True, verbose_name="Motif d'annulation")

    # Récurrence
    recurrence = models.CharField(
        max_length=10, choices=RECURRENCE_CHOICES, default='none', verbose_name="Récurrence"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'training_sessions'
        verbose_name = "Séance d'entraînement"
        verbose_name_plural = "Séances d'entraînement"
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.team} – Entraînement {self.date} {self.start_time}"

    def clean(self):
        super().clean()
        # Validate: start_time must be before end_time
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({
                'end_time': "L'heure de fin doit être après l'heure de début."
            })
        # Validate: no overlapping sessions for same team on same date
        if self.team_id and self.date and self.start_time and self.end_time:
            overlapping = TrainingSession.objects.filter(
                team=self.team,
                date=self.date,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(
                    "Une séance d'entraînement existe déjà à ce créneau horaire pour cette équipe."
                )


class Event(models.Model):
    """
    Événement sportif : match, tournoi ou événement divers.
    """

    TYPE_CHOICES = [
        ('match', 'Match'),
        ('tournament', 'Tournoi'),
        ('event', 'Événement'),
        ('friendly', 'Match amical'),
        ('other', 'Autre'),
    ]

    STATUS_CHOICES = [
        ('scheduled', 'Planifié'),
        ('cancelled', 'Annulé'),
        ('postponed', 'Reporté'),
        ('finished', 'Terminé'),
    ]

    # Relations
    team = models.ForeignKey(
        'teams.Team', on_delete=models.CASCADE,
        related_name='events', verbose_name="Équipe"
    )
    season = models.ForeignKey(
        'teams.Season', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='events', verbose_name="Saison"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_events'
    )

    # Informations générales
    event_type = models.CharField(
        max_length=15, choices=TYPE_CHOICES, default='match', verbose_name="Type d'événement"
    )
    title = models.CharField(max_length=200, verbose_name="Titre")
    opponent = models.CharField(max_length=200, blank=True, verbose_name="Adversaire")
    location = models.CharField(max_length=200, verbose_name="Lieu")

    # Planification
    date = models.DateField(verbose_name="Date")
    start_time = models.TimeField(verbose_name="Heure de début")
    end_time = models.TimeField(null=True, blank=True, verbose_name="Heure de fin")

    # Statut
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='scheduled', verbose_name="Statut"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'planning_events'
        verbose_name = 'Événement'
        verbose_name_plural = 'Événements'
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.get_event_type_display()} – {self.title} ({self.date})"

    def clean(self):
        super().clean()
        # Validate: start_time must be before end_time (when end_time is set)
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({
                'end_time': "L'heure de fin doit être après l'heure de début."
            })
        # Validate: no overlapping events for same team on same date
        if self.team_id and self.date and self.start_time:
            filters = {
                'team': self.team,
                'date': self.date,
            }
            if self.end_time:
                overlapping = Event.objects.filter(
                    **filters,
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time,
                ).exclude(pk=self.pk)
            else:
                # No end_time: check exact start_time match
                overlapping = Event.objects.filter(
                    **filters,
                    start_time=self.start_time,
                ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(
                    "Un événement existe déjà à ce créneau horaire pour cette équipe."
                )


class Convocation(models.Model):
    """
    Convocation d'un joueur pour un événement.
    Créée automatiquement lors de la création d'un Event.
    Le parent peut approuver ou rejeter la convocation.
    """
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('approved', 'Approuvé'),
        ('rejected', 'Refusé'),
    ]

    player = models.ForeignKey(
        'teams.Player', on_delete=models.CASCADE,
        related_name='convocations', verbose_name="Joueur"
    )

    # Lié à un événement (one convocation set per event)
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE,
        related_name='convocations', verbose_name="Événement"
    )

    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name="Statut"
    )
    notified = models.BooleanField(default=False, verbose_name="Notification envoyée")
    notified_at = models.DateTimeField(null=True, blank=True, verbose_name="Date de notification")
    parent_response_at = models.DateTimeField(null=True, blank=True, verbose_name="Date de réponse du parent")
    notes = models.TextField(blank=True, verbose_name="Notes")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'convocations'
        verbose_name = 'Convocation'
        verbose_name_plural = 'Convocations'
        unique_together = ['player', 'event']
        ordering = ['player__jersey_number']

    def __str__(self):
        return f"Convocation de {self.player.full_name} – {self.event.title}"
