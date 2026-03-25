from rest_framework.exceptions import PermissionDenied
from rest_framework import viewsets, mixins, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg

from .models import Club, Team, Player, Season, Category, Coach
from .serializers import (
    ClubSerializer, TeamSerializer, PlayerSerializer,
    SeasonSerializer, CategorySerializer, CoachSerializer,
)
from users.permissions import (
    IsAdminOrStaffUserType, IsStaffUserType,
    IsAdminOrStaffOrParentUserType, IsStaffOrCoachUserType,
    IsStaffOrCoachOrParentUserType,
    IsAdminOrStaffOrCoachOrParentUserType
)


# ─────────────────────────────────────────────
# Season
# ─────────────────────────────────────────────

class SeasonViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Saisons — lecture seule + export PDF + recalcul stats.
    Les saisons sont créées automatiquement lors de la création d'une équipe.
    Nested under: /clubs/<club_pk>/teams/<team_pk>/seasons/
    """
    serializer_class = SeasonSerializer

    def _is_staff_owner(self, team):
        return self.request.user.user_type == 'staff' and team.club.owner == self.request.user

    def _is_team_coach(self, team):
        return getattr(self.request.user, 'user_type', None) == 'coach' and team.coach == self.request.user

    def get_permissions(self):
        return [IsStaffOrCoachUserType()]

    def get_queryset(self):
        user = self.request.user
        team_id = self.kwargs.get('team_pk')
        if team_id:
            team = get_object_or_404(Team, pk=team_id)
            if self._is_staff_owner(team) or self._is_team_coach(team):
                return Season.objects.filter(team=team)
            raise PermissionDenied({'error': 'You can only access seasons for your own teams.'})
        if getattr(user, 'user_type', None) == 'staff':
            return Season.objects.filter(team__club__owner=user)
        return Season.objects.filter(team__coach=user)

    @action(detail=True, methods=['get'], url_path='export-pdf')
    def export_pdf(self, request, **kwargs):
        """Download a PDF report for a season."""
        from django.http import HttpResponse
        from .pdf_export import generate_season_pdf

        season = self.get_object()
        pdf_buffer = generate_season_pdf(season)

        team_name = season.team.name if season.team else 'team'
        filename = f"saison_{season.name}_{team_name}.pdf".replace(' ', '_')

        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=['post'])
    def recalculate(self, request, **kwargs):
        """Recalculate all season stats from scratch (match data)."""
        from .season_stats import recalculate_season_stats

        season = self.get_object()
        if season.team and not (self._is_staff_owner(season.team) or self._is_team_coach(season.team)):
            raise PermissionDenied({'error': 'You can only recalculate stats for your own teams.'})

        recalculate_season_stats(season)
        season.refresh_from_db()
        serializer = self.get_serializer(season)
        return Response({
            'message': 'Statistiques recalculées avec succès.',
            'season': serializer.data,
        })


# ─────────────────────────────────────────────
# Category
# ─────────────────────────────────────────────

class CategoryViewSet(viewsets.ModelViewSet):
    """Catégories d'âge d'un club."""
    serializer_class = CategorySerializer

    def get_queryset(self):
        club_id = self.kwargs.get('club_pk') or self.request.query_params.get('club_id')
        if club_id:
            return Category.objects.filter(club_id=club_id)
        return Category.objects.all()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrStaffOrParentUserType()]
        return [IsAdminOrStaffUserType()]

    def perform_create(self, serializer):
        club_id = self.kwargs.get('club_pk')
        club = get_object_or_404(Club, pk=club_id) if club_id else None
        serializer.save(club=club) if club else serializer.save()


# ─────────────────────────────────────────────
# Coach
# ─────────────────────────────────────────────

class CoachViewSet(viewsets.ModelViewSet):
    """CRUD fiches coachs — staff only, own teams only."""
    serializer_class = CoachSerializer
    permission_classes = [IsStaffUserType]

    def get_queryset(self):
        """Only return coaches for teams in clubs the staff user owns."""
        team_id = self.kwargs.get('team_pk')
        if team_id:
            team = get_object_or_404(Team, pk=team_id)
            if team.club.owner != self.request.user:
                raise PermissionDenied({'error': 'You can only access coaches for your own teams.'})
            return Coach.objects.filter(team=team)
        # Fallback: return coaches only from teams in clubs owned by this user
        return Coach.objects.filter(team__club__owner=self.request.user)

    def perform_create(self, serializer):
        team_id = self.kwargs.get('team_pk')
        team = get_object_or_404(Team, pk=team_id)
        if team.club.owner != self.request.user:
            raise PermissionDenied({'error': 'You can only create coaches for your own teams.'})
        coach = serializer.save(team=team)
        # ── Sync: assign this coach's user account to the Team model ──
        team.coach = coach.user
        team.save(update_fields=['coach'])

    def perform_update(self, serializer):
        coach_profile = self.get_object()
        if coach_profile.team and coach_profile.team.club.owner != self.request.user:
            raise PermissionDenied({'error': 'You can only update coaches in your own teams.'})
        old_user = coach_profile.user
        updated_coach = serializer.save()
        # ── Sync: if the linked user changed, update Team.coach too ──
        if updated_coach.team and updated_coach.user != old_user:
            updated_coach.team.coach = updated_coach.user
            updated_coach.team.save(update_fields=['coach'])

    def perform_destroy(self, instance):
        if instance.team and instance.team.club.owner != self.request.user:
            raise PermissionDenied({'error': 'You can only delete coaches in your own teams.'})
        # ── Sync: clear the Team.coach field when the profile is deleted ──
        if instance.team and instance.team.coach == instance.user:
            instance.team.coach = None
            instance.team.save(update_fields=['coach'])
        instance.delete()


# ─────────────────────────────────────────────
# Club
# ─────────────────────────────────────────────

class ClubViewSet(viewsets.ModelViewSet):
    """ViewSet for managing clubs"""
    serializer_class = ClubSerializer
    permission_classes = [IsAdminOrStaffOrParentUserType]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        # Admin sees everything
        if getattr(user, 'user_type', '') == 'admin':
            return Club.objects.all()
        # Staff sees only their own clubs
        if getattr(user, 'user_type', '') == 'staff':
            return Club.objects.filter(owner=user)
        # Coach sees clubs of teams they coach
        if getattr(user, 'user_type', '') == 'coach':
            return Club.objects.filter(teams__coach=user).distinct()
        # Parent sees clubs of teams they follow or their children's teams
        if getattr(user, 'user_type', '') == 'parent':
            from django.db.models import Q
            return Club.objects.filter(
                Q(teams__followers=user) |
                Q(teams__players__father_email=user.email) |
                Q(teams__players__mother_email=user.email)
            ).distinct()
        return Club.objects.none()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAdminOrStaffOrCoachOrParentUserType]
        else:
            permission_classes = [permissions.IsAuthenticated, IsStaffUserType]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        if self.request.user.user_type != 'staff':
            raise PermissionDenied({'error': 'Only staff users can create clubs'})
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        club = self.get_object()
        if club.owner != self.request.user:
            raise PermissionDenied({'error': 'Only the owner can update the club'})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.owner != self.request.user:
            raise PermissionDenied({'error': 'Only the owner can delete the club'})
        instance.delete()


class MyClubView(ListAPIView):
    serializer_class = ClubSerializer
    permission_classes = [IsAdminOrStaffOrParentUserType]

    def get_queryset(self):
        return Club.objects.filter(owner=self.request.user)


# ─────────────────────────────────────────────
# Team
# ─────────────────────────────────────────────

class TeamViewSet(viewsets.ModelViewSet):

    serializer_class = TeamSerializer
    permission_classes = [IsStaffOrCoachOrParentUserType]

    def get_queryset(self):
        user = self.request.user
        club_id = self.kwargs.get('club_pk')
        base_qs = Team.objects.all()

        if club_id:
            base_qs = base_qs.filter(club_id=club_id)

        # Admin sees everything
        if getattr(user, 'user_type', '') == 'admin':
            return base_qs

        # Staff sees only teams in clubs they own
        if getattr(user, 'user_type', '') == 'staff':
            return base_qs.filter(club__owner=user)

        # Coach sees only teams they coach
        if getattr(user, 'user_type', '') == 'coach':
            return base_qs.filter(coach=user)

        # Parent sees teams they follow or their children's teams
        if getattr(user, 'user_type', '') == 'parent':
            return base_qs.filter(
                Q(followers=user) |
                Q(players__father_email=user.email) |
                Q(players__mother_email=user.email)
            ).distinct()

        return Team.objects.none()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAdminOrStaffOrCoachOrParentUserType]
        else:
            permission_classes = [permissions.IsAuthenticated, IsStaffUserType]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        club_id = self.kwargs.get('club_pk')
        club = get_object_or_404(Club, pk=club_id)
        if club.owner != self.request.user:
            raise PermissionDenied({'error': 'Only Club staff users can create teams'})
        serializer.save(club=club)

    def perform_update(self, serializer):
        team = self.get_object()
        if team.club.owner != self.request.user:
            raise PermissionDenied({'error': 'Only the owner can update the team'})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.club.owner != self.request.user:
            raise PermissionDenied({'error': 'Only the owner can delete the team'})
        instance.delete()


class MyTeamView(ListAPIView):
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Team.objects.filter(
            Q(club__owner=user) |
            Q(coach=user) |
            Q(followers=user)
        ).distinct()


class MyPlayersView(ListAPIView):
    serializer_class = PlayerSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrStaffOrParentUserType]

    def get_queryset(self):
        user = self.request.user
        return Player.objects.filter(
            Q(team__followers=user) |
            Q(father_email=user.email) |
            Q(mother_email=user.email)
        ).distinct()


# ─────────────────────────────────────────────
# Player
# ─────────────────────────────────────────────

class PlayerViewSet(viewsets.ModelViewSet):
    queryset = Player.objects.all()
    serializer_class = PlayerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Player.objects.all()
        team_id = self.kwargs.get('team_pk') or self.request.query_params.get('team_id')
        is_main = self.request.query_params.get('is_main_player')
        status_filter = self.request.query_params.get('status')

        if team_id:
            queryset = queryset.filter(team_id=team_id)
        if is_main is not None:
            val = str(is_main).lower()
            queryset = queryset.filter(is_main_player=(val in ('true', '1')))
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAdminOrStaffOrParentUserType]
        else:
            permission_classes = [permissions.IsAuthenticated, IsStaffUserType]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        team_id = self.kwargs.get('team_pk')
        team = get_object_or_404(Team, pk=team_id)
        if (team.club.owner != self.request.user) and (team.coach != self.request.user):
            raise PermissionDenied({'error': 'Only the owner or the coach can create players'})
        serializer.is_valid(raise_exception=True)
        serializer.save(team=team)

    def perform_update(self, serializer):
        player = self.get_object()
        if player.team.club.owner != self.request.user and player.team.coach != self.request.user:
            raise PermissionDenied({'error': 'Only the owner or the coach can update the player'})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.team.club.owner != self.request.user and instance.team.coach != self.request.user:
            raise PermissionDenied({'error': 'Only the owner or the coach can delete the player'})
        instance.delete()

    @action(detail=False, methods=['get'])
    def main_players(self, request, *args, **kwargs):
        """Get all main players (starting 11) for a team"""
        team_id = kwargs.get('team_pk') or request.query_params.get('team_id')
        if not team_id:
            return Response({'error': 'team_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        team = get_object_or_404(Team, id=team_id)
        main_players = team.players.filter(is_main_player=True, is_active=True)
        serializer = self.get_serializer(main_players, many=True)
        return Response({'team': team.name, 'count': main_players.count(), 'max_allowed': 11, 'players': serializer.data})

    @action(detail=False, methods=['get'])
    def substitute_players(self, request, *args, **kwargs):
        """Get all substitute players for a team"""
        team_id = kwargs.get('team_pk') or request.query_params.get('team_id')
        if not team_id:
            return Response({'error': 'team_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        team = get_object_or_404(Team, id=team_id)
        subs = team.players.filter(is_main_player=False, is_active=True)
        serializer = self.get_serializer(subs, many=True)
        return Response({'team': team.name, 'count': subs.count(), 'players': serializer.data})

    @action(detail=True, methods=['post'])
    def set_as_main(self, request, pk=None, *args, **kwargs):
        player = self.get_object()
        if player.team.club.owner != request.user and player.team.coach != request.user:
            raise PermissionDenied({'error': 'Only the owner or the coach can modify main players'})
        main_count = Player.objects.filter(team=player.team, is_main_player=True, is_active=True).exclude(pk=player.pk).count()
        if main_count >= 11:
            return Response({'error': 'Cette équipe a déjà 11 joueurs titulaires'}, status=status.HTTP_400_BAD_REQUEST)
        player.is_main_player = True
        player.save()
        return Response({'message': f'{player.full_name} est maintenant joueur titulaire', 'player': self.get_serializer(player).data})

    @action(detail=True, methods=['post'])
    def remove_as_main(self, request, pk=None, *args, **kwargs):
        player = self.get_object()
        if player.team.club.owner != request.user and player.team.coach != request.user:
            raise PermissionDenied({'error': 'Only the owner or the coach can modify main players'})
        player.is_main_player = False
        player.save()
        return Response({'message': f"{player.full_name} n'est plus joueur titulaire", 'player': self.get_serializer(player).data})


# ─────────────────────────────────────────────
# Public & Security views
# ─────────────────────────────────────────────

class PublicTeamViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for public/parent team access"""
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrStaffOrParentUserType]
    pagination_class = None

    def get_queryset(self):
        queryset = Team.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    @action(detail=True, methods=['get'])
    def players(self, request, pk=None):
        team = self.get_object()
        players = Player.objects.filter(team=team, is_active=True)
        serializer = PlayerSerializer(players, many=True)
        return Response({'results': serializer.data})
