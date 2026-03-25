from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import TrainingSession, Event, Convocation
from .serializers import TrainingSessionSerializer, EventSerializer, ConvocationSerializer
from users.permissions import IsStaffOrCoachOrParentUserType, IsStaffOrCoachUserType


# ─────────────────────────────────────────────────────────────
# Shared access helpers
# ─────────────────────────────────────────────────────────────

def _is_staff_owner(user, team):
    """Staff can manage the team if they own the team's club."""
    return user.user_type == 'staff' and team.club.owner == user


def _is_team_coach(user, team):
    """Coach can manage the team if they are directly assigned as team.coach."""
    return user.user_type == 'coach' and team.coach == user


def _can_manage(user, team):
    return _is_staff_owner(user, team) or _is_team_coach(user, team)


def _get_team_from_url(kwargs):
    """Get team object from nested URL kwargs (team_pk)."""
    from teams.models import Team
    team_pk = kwargs.get('team_pk')
    return get_object_or_404(Team.objects.select_related('club'), pk=team_pk)


# ─────────────────────────────────────────────────────────────
# TrainingSession
# ─────────────────────────────────────────────────────────────

class TrainingSessionViewSet(viewsets.ModelViewSet):
    """
    Gestion des séances d'entraînement.
    Nested under: /clubs/<club_pk>/teams/<team_pk>/training-sessions/
    - Staff  : CRUD pour les équipes des clubs qu'ils possèdent
    - Coach  : CRUD pour leur équipe uniquement
    - Parent : lecture seule
    """
    serializer_class = TrainingSessionSerializer

    def get_queryset(self):
        user = self.request.user
        team = _get_team_from_url(self.kwargs)

        queryset = TrainingSession.objects.select_related(
            'team', 'team__club', 'category', 'coach', 'season'
        ).filter(team=team)

        if user.user_type == 'staff':
            if team.club.owner != user:
                return queryset.none()
        elif user.user_type == 'coach':
            if team.coach != user:
                return queryset.none()
        elif user.user_type == 'parent':
            has_child = team.players.filter(
                Q(father_email=user.email) | Q(mother_email=user.email)
            ).exists()
            if not has_child:
                return queryset.none()

        # Optional filters
        coach_id    = self.request.query_params.get('coach_id')
        category_id = self.request.query_params.get('category_id')
        season_id   = self.request.query_params.get('season_id')
        date_from   = self.request.query_params.get('date_from')
        date_to     = self.request.query_params.get('date_to')

        if coach_id:
            queryset = queryset.filter(coach_id=coach_id)
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        if season_id:
            queryset = queryset.filter(season_id=season_id)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsStaffOrCoachOrParentUserType()]
        return [IsStaffOrCoachUserType()]

    def perform_create(self, serializer):
        team = _get_team_from_url(self.kwargs)
        if not _can_manage(self.request.user, team):
            raise PermissionDenied({'error': 'You can only create training sessions for your own teams.'})
        serializer.save(team=team, created_by=self.request.user)

    def perform_update(self, serializer):
        session = self.get_object()
        if not _can_manage(self.request.user, session.team):
            raise PermissionDenied({'error': 'You can only update training sessions for your own teams.'})
        serializer.save()

    def perform_destroy(self, instance):
        if not _can_manage(self.request.user, instance.team):
            raise PermissionDenied({'error': 'You can only delete training sessions for your own teams.'})
        instance.delete()


# ─────────────────────────────────────────────────────────────
# Event
# ─────────────────────────────────────────────────────────────

class EventViewSet(viewsets.ModelViewSet):
    """
    Gestion des événements (matchs, tournois, …).
    Nested under: /clubs/<club_pk>/teams/<team_pk>/events/
    - Staff  : CRUD pour les équipes des clubs qu'ils possèdent
    - Coach  : CRUD pour leur équipe uniquement
    - Parent : lecture seule
    La création d'un Event génère automatiquement les Convocations
    pour tous les joueurs actifs de l'équipe.
    """
    serializer_class = EventSerializer

    def get_queryset(self):
        user = self.request.user
        team = _get_team_from_url(self.kwargs)

        queryset = Event.objects.select_related(
            'team', 'team__club', 'season'
        ).prefetch_related(
            'convocations', 'convocations__player'
        ).filter(team=team)

        if user.user_type == 'staff':
            if team.club.owner != user:
                return queryset.none()
        elif user.user_type == 'coach':
            if team.coach != user:
                return queryset.none()
        elif user.user_type == 'parent':
            has_child = team.players.filter(
                Q(father_email=user.email) | Q(mother_email=user.email)
            ).exists()
            if not has_child:
                return queryset.none()

        # Optional filters
        event_type = self.request.query_params.get('event_type')
        season_id  = self.request.query_params.get('season_id')
        date_from  = self.request.query_params.get('date_from')
        date_to    = self.request.query_params.get('date_to')
        ev_status  = self.request.query_params.get('status')

        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if season_id:
            queryset = queryset.filter(season_id=season_id)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        if ev_status:
            queryset = queryset.filter(status=ev_status)

        return queryset

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsStaffOrCoachOrParentUserType()]
        return [IsStaffOrCoachUserType()]

    def perform_create(self, serializer):
        team = _get_team_from_url(self.kwargs)
        if not _can_manage(self.request.user, team):
            raise PermissionDenied({'error': 'You can only create events for your own teams.'})
        event = serializer.save(team=team, created_by=self.request.user)
        # Auto-create Convocations for every active player
        players = team.players.filter(is_active=True)
        convocations = [
            Convocation(
                player=player,
                event=event,
                status='pending',
                notified=True,
                notified_at=timezone.now(),
            )
            for player in players
        ]
        if convocations:
            Convocation.objects.bulk_create(convocations)

    def perform_update(self, serializer):
        event = self.get_object()
        if not _can_manage(self.request.user, event.team):
            raise PermissionDenied({'error': 'You can only update events for your own teams.'})
        serializer.save()

    def perform_destroy(self, instance):
        if not _can_manage(self.request.user, instance.team):
            raise PermissionDenied({'error': 'You can only delete events for your own teams.'})
        instance.delete()


# ─────────────────────────────────────────────────────────────
# Convocation (nested under Event)
# ─────────────────────────────────────────────────────────────

class ConvocationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Convocations — nested under events:
    /clubs/<club_pk>/teams/<team_pk>/events/<event_pk>/convocations/

    Convocations are auto-created when an Event is created.
    Each event has ONE set of convocations (one per player).

    The list returns all players with their approval status.
    Parents can approve or reject via the 'respond' action.
    """
    serializer_class = ConvocationSerializer

    def _get_event(self):
        """Resolve the event from the nested URL."""
        event_pk = self.kwargs.get('event_pk')
        return get_object_or_404(
            Event.objects.select_related('team', 'team__club'),
            pk=event_pk
        )

    def get_queryset(self):
        user = self.request.user
        event = self._get_event()
        team = event.team

        queryset = Convocation.objects.select_related(
            'player', 'event', 'event__team'
        ).filter(event=event)

        # Role-based access
        if user.user_type == 'staff':
            if team.club.owner != user:
                return queryset.none()
        elif user.user_type == 'coach':
            if team.coach != user:
                return queryset.none()
        elif user.user_type == 'parent':
            # Parents see only their children's convocations
            queryset = queryset.filter(
                Q(player__father_email=user.email) |
                Q(player__mother_email=user.email)
            )

        return queryset

    def get_permissions(self):
        if self.action == 'respond':
            return [IsStaffOrCoachOrParentUserType()]
        return [IsStaffOrCoachOrParentUserType()]

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None, **kwargs):
        """
        Parent responds to a convocation: approved / rejected.
        Only the parent of the concerned player may call this.
        """
        convocation = self.get_object()
        user = request.user

        # Only parents can respond
        if user.user_type != 'parent':
            raise PermissionDenied({'error': 'Seuls les parents peuvent répondre à une convocation.'})

        # Verify this parent is the player's parent
        player = convocation.player
        if user.email not in [player.father_email, player.mother_email]:
            raise PermissionDenied({'error': "Vous ne pouvez répondre qu'aux convocations de vos enfants."})

        new_status = request.data.get('status')
        if new_status not in ('approved', 'rejected'):
            return Response(
                {'error': "Statut invalide. Choisissez : 'approved' ou 'rejected'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        convocation.status = new_status
        convocation.parent_response_at = timezone.now()
        convocation.save(update_fields=['status', 'parent_response_at', 'updated_at'])
        return Response(ConvocationSerializer(convocation).data)
