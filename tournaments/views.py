from rest_framework import viewsets, status, permissions
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from rest_framework.exceptions import PermissionDenied, ValidationError
from teams.models import Team, Player
from matches.models import MatchLineup
from .services import TournamentEngine
from .serializers import KnockoutBracketSerializer, TournamentAutomationSerializer


from .models import (
    Tournament, TournamentGroup, TournamentPhase,
    TeamGroup, Match
)
from .serializers import (
    TournamentSerializer,
    TournamentGroupSerializer,
    TournamentPhaseSerializer,

    TournamentListSerializer,
    TournamentDetailSerializer,
    TeamGroupSerializer,
    AddTeamToGroupSerializer,
    MatchSerializer,
    CreateMatchSerializer,
    UpdateMatchScoreSerializer,
    GroupStandingsSerializer,
)
from users.permissions import IsAdminUserType, IsAdminActiveUserType, IsOrganizerOrSuperUser, IsMatchCoachOrAdmin, IsAdminOrStaffOrParentUserType, IsViewerOrAdminOrStaffOrParentUserType, IsStaffOrCoachOrParentUserType


class TournamentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tournaments"""
    queryset = Tournament.objects.all()
    serializer_class = TournamentSerializer
    permission_classes = [IsAdminOrStaffOrParentUserType]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_field = 'id'

    def get_queryset(self):
        """Filter tournaments based on user type"""
        user = self.request.user
        
        # If user is not authenticated, return empty queryset
        # (public endpoints should override this)
        if not user or not user.is_authenticated:
            return Tournament.objects.none()
        
        # Viewer users: can see ALL tournaments (read-only)
        if user.user_type == 'viewer':
            return Tournament.objects.all().order_by('-created_at')
        
        # Admin users: see only tournaments they created/organize
        if user.user_type == 'admin':
            return Tournament.objects.filter(organizer=user).order_by('-created_at')
        
        # Staff users: see tournaments where their club's teams participate
        elif user.user_type == 'staff':
            from teams.models import Club
            
            # Get clubs owned by this user
            user_clubs = Club.objects.filter(owner=user)
            
            # Filter tournaments where teams from these clubs participate
            queryset = Tournament.objects.filter(
                Q(teamtournamentregistration__team__club__in=user_clubs) |
                Q(groups__team_groups__team__club__in=user_clubs)
            ).distinct().order_by('-created_at')
            
            return queryset
        
        # Parent users: see tournaments where their children's teams participate
        elif user.user_type == 'parent':
            from teams.models import Player
            
            # Teams followed directly
            followed_teams_ids = list(Team.objects.filter(followers=user).values_list('id', flat=True))
            
            # Teams where user is parent of a player (by email - check both parent emails)
            if user.email:
                player_teams_ids = list(Player.objects.filter(
                    Q(father_email=user.email) | Q(mother_email=user.email)
                ).values_list('team_id', flat=True))
                followed_teams_ids.extend(player_teams_ids)
            
            # Unique team IDs
            team_ids = list(set(followed_teams_ids))
            
            queryset = Tournament.objects.filter(
                Q(teamtournamentregistration__team_id__in=team_ids) |
                Q(groups__team_groups__team_id__in=team_ids)
            ).distinct().order_by('-created_at')
            
            return queryset
        
        # Coach users: see tournaments where their coached teams participate
        elif user.user_type == 'coach':
            coached_teams = user.coached_teams.all()
            queryset = Tournament.objects.filter(
                Q(teamtournamentregistration__team__in=coached_teams) |
                Q(groups__team_groups__team__in=coached_teams)
            ).distinct().order_by('-created_at')
            return queryset
        
        # Default: return empty queryset for unknown user types
        return Tournament.objects.none()

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'groups', 'add_group', 'matches', 'create_match']:
            permission_classes = [permissions.AllowAny]
        elif self.action in ['create']:
            permission_classes = [IsAdminActiveUserType]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOrganizerOrSuperUser]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        if self.request.user.user_type != "admin":
            raise PermissionDenied("Seuls les admins peuvent créer des tournois.")
        serializer.save(organizer=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.organizer != self.request.user and not self.request.user.is_superuser:
            raise PermissionDenied("Vous ne pouvez modifier que vos propres tournois.")
        serializer.save()
    
    def perform_destroy(self, instance):
        if instance.organizer != self.request.user and not self.request.user.is_superuser:
            raise PermissionDenied("Vous ne pouvez supprimer que vos propres tournois.")
        instance.delete()
    
    @action(detail=False, methods=['get'], url_path='my-tournaments', permission_classes=[permissions.IsAuthenticated])
    def my_tournaments(self, request):
        """Get tournaments organized by the current user or where they follow a team
        Returns comprehensive tournament data including groups, teams, matches, standings, and phases"""
        if request.user.user_type == 'parent':
            # For parents, show tournaments where their followed teams are participating
            from teams.models import Player
            
            # Teams followed directly
            followed_teams_ids = list(Team.objects.filter(followers=request.user).values_list('id', flat=True))
            
            # Teams where user is parent of a player (by email - check both parent emails)
            if request.user.email:
                player_teams_ids = list(Player.objects.filter(
                    Q(father_email=request.user.email) | Q(mother_email=request.user.email)
                ).values_list('team_id', flat=True))
                followed_teams_ids.extend(player_teams_ids)
            
            # Unique team IDs
            team_ids = list(set(followed_teams_ids))
            
            queryset = Tournament.objects.filter(
                Q(teamtournamentregistration__team_id__in=team_ids) |
                Q(groups__team_groups__team_id__in=team_ids)
            ).distinct().order_by('-created_at')
            
            # Filter by specific team if provided
            team_id = request.query_params.get('team_id')
            if team_id:
                queryset = queryset.filter(
                    Q(teamtournamentregistration__team_id=team_id) |
                    Q(groups__team_groups__team_id=team_id)
                ).distinct()
                
        else:
            # For organizers/staff, show tournaments they organized
            queryset = Tournament.objects.filter(organizer=request.user).order_by('-created_at')
        
        # Optimize query with prefetch_related to avoid N+1 queries
        queryset = queryset.prefetch_related(
            'groups__team_groups__team__club',
            'phases',
            'tournament_matches__home_team__club',
            'tournament_matches__away_team__club',
            'tournament_matches__group',
            'tournament_matches__phase'
        ).select_related('organizer')
        
        # Use comprehensive serializer for full data
        from .serializers import ComprehensiveTournamentSerializer
        serializer = ComprehensiveTournamentSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get', 'post'], url_path='groups')
    def groups(self, request, id=None):
        """List or create groups in this tournament (nested)"""
        tournament = self.get_object()

        # List groups
        if request.method.lower() == 'get':
            groups = tournament.groups.prefetch_related('team_groups__team__club').all()
            serializer = TournamentGroupSerializer(groups, many=True)
            return Response(serializer.data)

        # Create group
        if request.method.lower() == 'post':
            if not request.user.is_authenticated:
                raise PermissionDenied("Authentification requise pour créer des groupes")
            if tournament.organizer != request.user and not request.user.is_superuser:
                raise PermissionDenied("Seul l'organisateur peut créer des groupes")

            data = request.data.copy()
            # Ensure the tournament field is not expected from client
            data.pop('tournament', None)

            serializer = TournamentGroupSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            group = serializer.save(tournament=tournament)
            return Response(TournamentGroupSerializer(group).data, status=status.HTTP_201_CREATED)

        return Response({"detail": "Méthode non supportée"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=['get', 'patch', 'delete'], url_path='groups/(?P<group_id>[^/.]+)')
    def group_detail(self, request, id=None, group_id=None):
        """Retrieve, update or delete a specific group within a tournament"""
        tournament = self.get_object()
        group = get_object_or_404(TournamentGroup, id=group_id, tournament=tournament)

        if request.method.lower() == 'get':
            return Response(TournamentGroupSerializer(group).data)

        # For update/delete, enforce organizer or superuser
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentification requise")
        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut modifier ou supprimer des groupes")

        if request.method.lower() == 'patch':
            serializer = TournamentGroupSerializer(group, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

        if request.method.lower() == 'delete':
            group.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response({"detail": "Méthode non supportée"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    @action(detail=True, methods=['post'], url_path='groups/create')
    def add_group(self, request, id=None):
        """Create a new group in this tournament"""
        tournament = self.get_object()
        
        # Check permissions
        if request.user.is_authenticated:
            if tournament.organizer != request.user and not request.user.is_superuser:
                raise PermissionDenied("Seul l'organisateur peut créer des groupes")
        
        # Create serializer with tournament data
        data = request.data.copy()
        data['tournament'] = tournament.id
        
        serializer = TournamentGroupSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tournament=tournament)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'], url_path='matches')
    def matches(self, request, id=None):
        """Get all matches in this tournament"""
        tournament = self.get_object()
        matches = tournament.tournament_matches.all()
        serializer = MatchSerializer(matches, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='matches/create')
    def create_match(self, request, id=None):
        """Create a new match in this tournament"""
        tournament = self.get_object()
        
        # Check permissions
        if request.user.is_authenticated:
            if tournament.organizer != request.user and not request.user.is_superuser:
                raise PermissionDenied("Seul l'organisateur peut créer des matchs")
        
        # Validate data
        serializer = CreateMatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get group if provided
        group_id = request.data.get('group_id')
        group = None
        if group_id:
            group = get_object_or_404(TournamentGroup, id=group_id, tournament=tournament)
            
        # Get phase if provided
        phase_id = request.data.get('phase_id')
        phase = None
        if phase_id:
            phase = get_object_or_404(TournamentPhase, id=phase_id, tournament=tournament)
        
        # Create the match
        match = Match.objects.create(
            tournament=tournament,
            group=group,
            phase=phase,
            home_team_id=serializer.validated_data['home_team_id'],
            away_team_id=serializer.validated_data['away_team_id'],
            match_date=serializer.validated_data['match_date'],
            venue=serializer.validated_data.get('venue', ''),
            round_number=serializer.validated_data.get('round_number', 1),
            match_number=serializer.validated_data.get('match_number'),
        )
        
        # Auto-populate lineups with main players for both teams
        home_team = match.home_team
        away_team = match.away_team
        
        if home_team:
            main_players = Player.objects.filter(team=home_team, is_main_player=True, is_active=True)
            for player in main_players:
                MatchLineup.objects.create(
                    match_id=match.id,
                    team=home_team,
                    player=player,
                    position=player.position,
                    is_starter=True,
                    minutes_played=0
                )
        
        if away_team:
            main_players = Player.objects.filter(team=away_team, is_main_player=True, is_active=True)
            for player in main_players:
                MatchLineup.objects.create(
                    match_id=match.id,
                    team=away_team,
                    player=player,
                    position=player.position,
                    is_starter=True,
                    minutes_played=0
                )
        
        return Response(
            MatchSerializer(match).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'], url_path='generate-group-matches')
    def generate_group_matches(self, request, id=None):
        """
        Auto-generate all group stage matches based on tournament rules.
        Call this after all teams have been assigned to groups.
        """
        tournament = self.get_object()

        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut générer les matchs")

        # Check there are no existing group matches
        existing = Match.objects.filter(tournament=tournament, group__isnull=False).count()
        if existing > 0:
            raise ValidationError(
                f"Il y a déjà {existing} matchs de groupe. "
                "Supprimez-les d'abord si vous voulez régénérer."
            )

        engine = TournamentEngine(tournament)
        try:
            matches = engine.generate_group_stage_matches()
        except ValueError as e:
            raise ValidationError(str(e))

        return Response({
            'message': f'{len(matches)} matchs de groupe générés automatiquement',
            'matches_created': len(matches),
            'matches': MatchSerializer(
                Match.objects.filter(tournament=tournament, group__isnull=False)
                .order_by('match_number'),
                many=True
            ).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='reset-group-matches')
    def reset_group_matches(self, request, id=None):
        """
        Delete all group stage matches for the tournament.
        """
        tournament = self.get_object()

        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut réinitialiser les matchs")

        group_matches = Match.objects.filter(tournament=tournament, group__isnull=False)
        deleted_count = group_matches.count()
        group_matches.delete()

        return Response({
            'message': f'{deleted_count} matchs de groupe supprimés',
            'matches_deleted': deleted_count
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='generate-knockout')
    def generate_knockout(self, request, id=None):
        """
        Generate knockout bracket after group stage is complete.
        Can also be triggered manually by the organizer.
        """
        tournament = self.get_object()

        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut générer le tableau éliminatoire")

        if tournament.bracket_generated:
            raise ValidationError("Le tableau éliminatoire a déjà été généré.")

        engine = TournamentEngine(tournament)
        try:
            created = engine.generate_knockout_bracket()
        except ValueError as e:
            raise ValidationError(str(e))

        phase_names = list(created.keys())
        total_matches = sum(len(m) for m in created.values())

        return Response({
            'message': f'Tableau éliminatoire généré: {total_matches} matchs',
            'matches_created': total_matches,
            'phases_created': phase_names,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='bracket')
    def bracket(self, request, id=None):
        """
        Get the full knockout bracket for display.
        Returns matches organized by phase/round.
        """
        tournament = self.get_object()

        knockout_phases = tournament.phases.exclude(
            phase_type='group_stage'
        ).order_by('order')

        bracket_data = []
        for phase in knockout_phases:
            matches = phase.matches.order_by('bracket_position', 'match_number')
            bracket_data.append({
                'phase_type': phase.phase_type,
                'phase_name': phase.name,
                'phase_order': phase.order,
                'is_completed': phase.is_completed,
                'matches': MatchSerializer(matches, many=True).data,
            })

        return Response(bracket_data)

    @action(detail=True, methods=['post'], url_path='reset-matches')
    def reset_matches(self, request, id=None):
        """
        Delete all generated matches (for re-generation).
        Only works if tournament hasn't started.
        """
        tournament = self.get_object()

        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut réinitialiser")

        match_type = request.data.get('type', 'all')  # 'all', 'group', 'knockout'

        if match_type == 'group':
            deleted, _ = Match.objects.filter(
                tournament=tournament, group__isnull=False
            ).delete()
        elif match_type == 'knockout':
            deleted, _ = Match.objects.filter(
                tournament=tournament, group__isnull=True, phase__isnull=False
            ).delete()
            tournament.bracket_generated = False
            tournament.save()
        else:
            deleted, _ = Match.objects.filter(tournament=tournament).delete()
            tournament.bracket_generated = False
            tournament.winner = None
            tournament.runner_up = None
            tournament.third_place = None
            tournament.save()

        # Reset qualification status
        TeamGroup.objects.filter(
            group__tournament=tournament
        ).update(is_qualified=False, qualified_position=None)

        return Response({
            'message': f'{deleted} matchs supprimés',
            'deleted_count': deleted,
        })

    @action(detail=True, methods=['get'], url_path='tournament-status')
    def tournament_status(self, request, id=None):
        """Get comprehensive tournament automation status."""
        tournament = self.get_object()

        group_matches = Match.objects.filter(tournament=tournament, group__isnull=False)
        knockout_matches = Match.objects.filter(
            tournament=tournament, group__isnull=True, phase__isnull=False
        )

        return Response({
            'tournament_type': tournament.tournament_type,
            'status': tournament.status,
            'group_stage': {
                'total_matches': group_matches.count(),
                'finished_matches': group_matches.filter(status='finished').count(),
                'live_matches': group_matches.filter(status='live').count(),
                'scheduled_matches': group_matches.filter(status='scheduled').count(),
                'is_complete': tournament.group_stage_complete,
            },
            'knockout_stage': {
                'bracket_generated': tournament.bracket_generated,
                'total_matches': knockout_matches.count(),
                'finished_matches': knockout_matches.filter(status='finished').count(),
                'placeholder_matches': knockout_matches.filter(
                    Q(home_team__isnull=True) | Q(away_team__isnull=True)
                ).count(),
                'is_complete': tournament.knockout_stage_complete,
            },
            'winner': tournament.winner.name if tournament.winner else None,
            'runner_up': tournament.runner_up.name if tournament.runner_up else None,
            'third_place': tournament.third_place.name if tournament.third_place else None,
        })


class TournamentGroupViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tournament groups"""
    queryset = TournamentGroup.objects.all()
    serializer_class = TournamentGroupSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return TournamentGroup.objects.prefetch_related('team_groups__team__club').all()
    
    def get_permissions(self):    
        permission_classes = [IsAdminActiveUserType]
        return [permission() for permission in permission_classes]
    
    @action(detail=True, methods=['get'], url_path='teams')
    def teams(self, request, pk=None):
        """Get all teams in a group"""
        group = self.get_object()
        team_groups = group.team_groups.select_related('team__club').all()
        serializer = TeamGroupSerializer(team_groups, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='add-team')
    def add_team(self, request, pk=None):
        """Add a team to a group by team ID"""
        group = self.get_object()
        tournament = group.tournament
        
        # Check permissions
        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut ajouter des équipes")
        
        serializer = AddTeamToGroupSerializer(
            data=request.data,
            context={'group': group}
        )
        serializer.is_valid(raise_exception=True)
        
        team_id = serializer.validated_data['team_id']
        position = serializer.validated_data.get('position')
        
        team = get_object_or_404(Team.objects.select_related('club'), id=team_id)
        
        # Create team-group relationship
        team_group = TeamGroup.objects.create(
            team=team,
            group=group,
            position=position
        )
        
        # Reload with related data
        team_group = TeamGroup.objects.select_related('team__club', 'group').get(id=team_group.id)
        
        return Response(
            TeamGroupSerializer(team_group).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['delete'], url_path='remove-team/(?P<team_id>[^/.]+)')
    def remove_team(self, request, pk=None, team_id=None):
        """Remove a team from a group"""
        group = self.get_object()
        tournament = group.tournament
        
        # Check permissions
        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut retirer des équipes")
        
        team_group = get_object_or_404(TeamGroup, group=group, team_id=team_id)
        team_group.delete()
        
        return Response(
            {'message': 'Équipe retirée du groupe'},
            status=status.HTTP_204_NO_CONTENT
        )
    
    @action(detail=True, methods=['get'], url_path='standings')
    def standings(self, request, pk=None):
        """Get group standings/classement"""
        group = self.get_object()
        standings = group.get_standings()
        serializer = GroupStandingsSerializer(standings, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'], url_path='matches')
    def matches(self, request, pk=None):
        """Get all matches in a group"""
        group = self.get_object()
        matches = group.matches.all()
        serializer = MatchSerializer(matches, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='create-match')
    def create_match(self, request, pk=None):
        """Create a match in this group"""
        group = self.get_object()
        tournament = group.tournament
        
        # Check permissions
        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut créer des matchs")
        
        serializer = CreateMatchSerializer(
            data=request.data,
            context={'group': group}
        )
        serializer.is_valid(raise_exception=True)
        
        # Get phase if provided
        phase_id = request.data.get('phase_id')
        phase = None
        if phase_id:
            phase = get_object_or_404(TournamentPhase, id=phase_id, tournament=tournament)

        # Create the match
        match = Match.objects.create(
            tournament=tournament,
            group=group,
            phase=phase,
            home_team_id=serializer.validated_data['home_team_id'],
            away_team_id=serializer.validated_data['away_team_id'],
            match_date=serializer.validated_data['match_date'],
            venue=serializer.validated_data.get('venue', ''),
            round_number=serializer.validated_data.get('round_number', 1),
            match_number=serializer.validated_data.get('match_number'),
        )
        
        # Auto-populate lineups with main players for both teams
        home_team = match.home_team
        away_team = match.away_team
        
        if home_team:
            main_players = Player.objects.filter(team=home_team, is_main_player=True, is_active=True)
            for player in main_players:
                MatchLineup.objects.create(
                    match_id=match.id,
                    team=home_team,
                    player=player,
                    position=player.position,
                    is_starter=True,
                    minutes_played=0
                )
        
        if away_team:
            main_players = Player.objects.filter(team=away_team, is_main_player=True, is_active=True)
            for player in main_players:
                MatchLineup.objects.create(
                    match_id=match.id,
                    team=away_team,
                    player=player,
                    position=player.position,
                    is_starter=True,
                    minutes_played=0
                )
        
        return Response(
            MatchSerializer(match).data,
            status=status.HTTP_201_CREATED
        )


class MatchViewSet(viewsets.ModelViewSet):
    """ViewSet for managing matches"""
    queryset = Match.objects.all()
    serializer_class = MatchSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.IsAuthenticated, IsViewerOrAdminOrStaffOrParentUserType]
        else:
            permission_classes = [permissions.IsAuthenticated, IsAdminActiveUserType]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """Filter matches by tournament, group, or phase"""
        queryset = Match.objects.all()
        user = self.request.user
        
        if not user.is_authenticated:
            return Match.objects.none()

        # Role-based filtering
        # Viewer users: can see ALL matches (read-only)
        if user.user_type == 'viewer':
            # Viewers can see all matches, no filtering needed
            pass
        elif user.user_type == 'admin':
            # Admin: only see matches from tournaments they organized
            queryset = queryset.filter(tournament__organizer=user)
            
        elif user.user_type == 'staff':
            # Staff: see matches where their club's teams participate
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            queryset = queryset.filter(
                Q(home_team__club__in=user_clubs) | 
                Q(away_team__club__in=user_clubs)
            ).distinct()
            
        elif user.user_type == 'parent':
            # Parent: see matches where their children's teams participate
            from teams.models import Player
            
            # Teams followed directly
            followed_teams_ids = list(Team.objects.filter(followers=user).values_list('id', flat=True))
            
            # Teams where user is parent of a player (by email - check both parent emails)
            if user.email:
                player_teams_ids = list(Player.objects.filter(
                    Q(father_email=user.email) | Q(mother_email=user.email)
                ).values_list('team_id', flat=True))
                followed_teams_ids.extend(player_teams_ids)
            
            # Unique team IDs
            team_ids = list(set(followed_teams_ids))
            
            queryset = queryset.filter(
                Q(home_team_id__in=team_ids) | 
                Q(away_team_id__in=team_ids)
            ).distinct()
        
        # Apply filters from query params
        tournament_id = self.request.query_params.get('tournament')
        group_id = self.request.query_params.get('group')
        phase_id = self.request.query_params.get('phase')
        match_status = self.request.query_params.get('status')
        
        if tournament_id:
            queryset = queryset.filter(tournament_id=tournament_id)
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        if phase_id:
            queryset = queryset.filter(phase_id=phase_id)
        if match_status:
            if match_status == 'upcoming':
                queryset = queryset.filter(status='scheduled')
            elif match_status == 'live':
                queryset = queryset.filter(Q(status='live') | Q(status='half_time'))
            else:
                queryset = queryset.filter(status=match_status)
            
        # Add team filter
        team_id = self.request.query_params.get('team')
        if team_id:
            queryset = queryset.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))
            
        # Add search filter
        search_query = self.request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(home_team__name__icontains=search_query) | 
                Q(away_team__name__icontains=search_query) |
                Q(home_team_placeholder__icontains=search_query) |
                Q(away_team_placeholder__icontains=search_query)
            )
        
        return queryset
    
    @action(detail=True, methods=['patch'], url_path='update-score')
    def update_score(self, request, pk=None):
        """Update match score and status"""
        match = self.get_object()
        tournament = match.tournament
        
        # Check permissions
        # Check permissions
        perm = IsMatchCoachOrAdmin()
        is_organizer = tournament.organizer == request.user or request.user.is_superuser
        
        if not is_organizer and not perm.has_object_permission(request, self, match):
            raise PermissionDenied("Seul l'organisateur ou les coachs peuvent mettre à jour les scores")
        
        serializer = UpdateMatchScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        match.home_score = serializer.validated_data['home_score']
        match.away_score = serializer.validated_data['away_score']
        
        if 'status' in serializer.validated_data:
            match.status = serializer.validated_data['status']
        
        match.save()
         
        return Response(MatchSerializer(match).data)
    
    @action(detail=True, methods=['post'], url_path='start')
    def start_match(self, request, pk=None):
        """Start a match"""
        match = self.get_object()
        tournament = match.tournament
        
        perm = IsMatchCoachOrAdmin()
        is_organizer = tournament.organizer == request.user or request.user.is_superuser
        
        if not is_organizer and not perm.has_object_permission(request, self, match):
            raise PermissionDenied("Seul l'organisateur ou les coachs peuvent démarrer les matchs")
        
        if match.status != 'scheduled':
            raise ValidationError("Seuls les matchs programmés peuvent être démarrés")
        
        match.status = 'live'
        match.save()
        
        return Response(MatchSerializer(match).data)

    @action(detail=True, methods=['post'], url_path='finish')
    def finish_match(self, request, pk=None):
        """Finish a match — triggers automatic winner propagation."""
        match = self.get_object()
        tournament = match.tournament

        perm = IsMatchCoachOrAdmin()
        is_organizer = tournament.organizer == request.user or request.user.is_superuser

        if not is_organizer and not perm.has_object_permission(request, self, match):
            raise PermissionDenied("Seul l'organisateur ou les coachs peuvent terminer les matchs")

        if match.status not in ['live', 'scheduled']:
            raise ValidationError("Le match doit être en cours ou programmé")

        # Check for draws in knockout matches (not allowed without extra logic)
        if match.is_knockout and match.home_score == match.away_score:
            raise ValidationError(
                "Les matchs éliminatoires ne peuvent pas se terminer par un nul. "
                "Mettez à jour le score avant de terminer."
            )

        match.status = 'finished'
        match.save()

        return Response(MatchSerializer(match).data)


class TournamentPhaseViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tournament phases"""
    queryset = TournamentPhase.objects.all()
    serializer_class = TournamentPhaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'matches']:
            permission_classes = [IsAdminOrStaffOrParentUserType]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminActiveUserType]
        return [permission() for permission in permission_classes]
    
    def perform_update(self, serializer):
        """Check if user is the tournament organizer before updating"""
        phase = self.get_object()
        tournament = phase.tournament
        if tournament.organizer != self.request.user and not self.request.user.is_superuser:
            raise PermissionDenied("Only the tournament organizer can update phases")
        serializer.save()
    
    def perform_destroy(self, instance):
        """Check if user is the tournament organizer before deleting"""
        tournament = instance.tournament
        if tournament.organizer != self.request.user and not self.request.user.is_superuser:
            raise PermissionDenied("Only the tournament organizer can delete phases")
        instance.delete()


# Specific API views for tournament operations
class TournamentTeamsView(APIView):
    """Get all teams registered in a tournament"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, tournament_id):
        tournament = get_object_or_404(Tournament, id=tournament_id)
        
        # Check permissions
        user = request.user
        if user.user_type == 'admin':
            if tournament.organizer != user:
                raise PermissionDenied("Vous ne pouvez voir que vos propres tournois")
        elif user.user_type == 'staff':
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            has_access = tournament.teamtournamentregistration_set.filter(team__club__in=user_clubs).exists() or \
                         tournament.groups.filter(team_groups__team__club__in=user_clubs).exists()
            if not has_access:
                raise PermissionDenied("Accès restreint aux tournois de votre club")
        elif user.user_type == 'parent':
            from teams.models import Player
            followed_teams_ids = list(Team.objects.filter(followers=user).values_list('id', flat=True))
            if user.email:
                player_teams_ids = list(Player.objects.filter(
                    Q(father_email=user.email) | Q(mother_email=user.email)
                ).values_list('team_id', flat=True))
                followed_teams_ids.extend(player_teams_ids)
            has_access = tournament.teamtournamentregistration_set.filter(team_id__in=followed_teams_ids).exists() or \
                         tournament.groups.filter(team_groups__team_id__in=followed_teams_ids).exists()
            if not has_access:
                raise PermissionDenied("Accès restreint aux tournois de vos équipes")

        # Get all teams through team-group relationships
        team_groups = TeamGroup.objects.filter(
            group__tournament=tournament
        ).select_related('team__club', 'group')
        
        serializer = TeamGroupSerializer(team_groups, many=True)
        return Response(serializer.data)





class TournamentStandingsView(APIView):
    """Get tournament standings (all groups)"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, tournament_id):
        tournament = get_object_or_404(Tournament, id=tournament_id)
        
        # Check permissions
        user = request.user
        if user.user_type == 'admin':
            if tournament.organizer != user:
                raise PermissionDenied("Vous ne pouvez voir que vos propres tournois")
        elif user.user_type == 'staff':
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            has_access = tournament.teamtournamentregistration_set.filter(team__club__in=user_clubs).exists() or \
                         tournament.groups.filter(team_groups__team__club__in=user_clubs).exists()
            if not has_access:
                raise PermissionDenied("Accès restreint aux tournois de votre club")
        elif user.user_type == 'parent':
            from teams.models import Player
            followed_teams_ids = list(Team.objects.filter(followers=user).values_list('id', flat=True))
            if user.email:
                player_teams_ids = list(Player.objects.filter(
                    Q(father_email=user.email) | Q(mother_email=user.email)
                ).values_list('team_id', flat=True))
                followed_teams_ids.extend(player_teams_ids)
            has_access = tournament.teamtournamentregistration_set.filter(team_id__in=followed_teams_ids).exists() or \
                         tournament.groups.filter(team_groups__team_id__in=followed_teams_ids).exists()
            if not has_access:
                raise PermissionDenied("Accès restreint aux tournois de vos équipes")
        elif user.user_type == 'coach':
            coached_teams = user.coached_teams.all()
            has_access = (
                tournament.groups.filter(team_groups__team__in=coached_teams).exists()
            )
            # Coaches can view standings for any tournament their teams participate in
            # If no teams registered yet, still allow read-only access
        
        standings_data = []
        # Prefetch related data for efficiency
        groups = tournament.groups.prefetch_related('team_groups__team__club').all()
        for group in groups:
            group_standings = group.get_standings()
            standings_data.append({
                'group_id': str(group.id),
                'group_name': group.name,
                'standings': GroupStandingsSerializer(group_standings, many=True).data
            })
        
        response_data = {
            'groups': standings_data
        }

        # Add winner/podium info (available for both league and knockout)
        knockout_data = {}
        if tournament.winner:
            knockout_data['winner'] = self._get_team_data(tournament.winner, request)
        if tournament.runner_up:
            knockout_data['runner_up'] = self._get_team_data(tournament.runner_up, request)
        if tournament.third_place:
            knockout_data['third_place'] = self._get_team_data(tournament.third_place, request)

        # Add knockout-specific stats if applicable
        if tournament.tournament_type != 'league':
            # Find semi finalists
            semi_finalists = []
            sf_matches = Match.objects.filter(tournament=tournament, phase__phase_type='semi_final')
            for match in sf_matches:
                loser = match.loser
                if loser and loser != tournament.third_place:
                    semi_finalists.append(self._get_team_data(loser, request))
            
            if semi_finalists:
                knockout_data['semi_finalists'] = semi_finalists
                
            # Find quarter finalists
            quarter_finalists = []
            qf_matches = Match.objects.filter(tournament=tournament, phase__phase_type='quarter_final')
            for match in qf_matches:
                loser = match.loser
                if loser:
                    quarter_finalists.append(self._get_team_data(loser, request))
                    
            if quarter_finalists:
                knockout_data['quarter_finalists'] = quarter_finalists
                
            # Find round of 16 finalists
            round_16_finalists = []
            r16_matches = Match.objects.filter(tournament=tournament, phase__phase_type='round_16')
            for match in r16_matches:
                loser = match.loser
                if loser:
                    round_16_finalists.append(self._get_team_data(loser, request))
                    
            if round_16_finalists:
                knockout_data['round_16_finalists'] = round_16_finalists
                
            # Add matches for all knockout phases
            knockout_phases = ['round_16', 'quarter_final', 'semi_final', 'third_place', 'final']
            knockout_matches_by_phase = []
            
            for p_type in knockout_phases:
                phase_matches = Match.objects.filter(tournament=tournament, phase__phase_type=p_type).order_by('match_date')
                if phase_matches.exists():
                    phase_obj = phase_matches.first().phase
                    phase_name = phase_obj.name if phase_obj else dict(Match.PHASE_TYPES).get(p_type, p_type.replace('_', ' ').title())
                    
                    serialized_matches = MatchSerializer(phase_matches, many=True, context={'request': request}).data
                    
                    knockout_matches_by_phase.append({
                        'phase_type': p_type,
                        'phase_name': phase_name,
                        'matches': serialized_matches
                    })
                    
            if knockout_matches_by_phase:
                knockout_data['phases'] = knockout_matches_by_phase
        
        # Only add knockout_data if it contains something (at least winner info)
        if knockout_data:
            response_data['knockout'] = knockout_data
        
        return Response(response_data)

    def _get_team_data(self, team, request):
        if not team:
            return None
        logo_url = team.club.logo.url if team.club and team.club.logo else None
        if logo_url and request:
            logo_url = request.build_absolute_uri(logo_url)
        return {
            'id': team.id,
            'name': team.name,
            'logo': logo_url
        }


class TournamentStatsView(APIView):
    """Get tournament statistics"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, tournament_id):
        tournament = get_object_or_404(Tournament, id=tournament_id)
        
        # Check permissions
        user = request.user
        if user.user_type == 'admin':
            if tournament.organizer != user:
                raise PermissionDenied("Vous ne pouvez voir que vos propres tournois")
        elif user.user_type == 'staff':
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            has_access = tournament.teamtournamentregistration_set.filter(team__club__in=user_clubs).exists() or \
                         tournament.groups.filter(team_groups__team__club__in=user_clubs).exists()
            if not has_access:
                raise PermissionDenied("Accès restreint aux tournois de votre club")
        elif user.user_type == 'parent':
            from teams.models import Player
            followed_teams_ids = list(Team.objects.filter(followers=user).values_list('id', flat=True))
            if user.email:
                player_teams_ids = list(Player.objects.filter(
                    Q(father_email=user.email) | Q(mother_email=user.email)
                ).values_list('team_id', flat=True))
                followed_teams_ids.extend(player_teams_ids)
            has_access = tournament.teamtournamentregistration_set.filter(team_id__in=followed_teams_ids).exists() or \
                         tournament.groups.filter(team_groups__team_id__in=followed_teams_ids).exists()
            if not has_access:
                raise PermissionDenied("Accès restreint aux tournois de vos équipes")
        
        stats = {
            'total_teams': TeamGroup.objects.filter(group__tournament=tournament).count(),
            'total_matches': Match.objects.filter(tournament=tournament).count(),
            'finished_matches': Match.objects.filter(tournament=tournament, status='finished').count(),
            'upcoming_matches': Match.objects.filter(tournament=tournament, status='scheduled').count(),
            'total_goals': Match.objects.filter(
                tournament=tournament, 
                status='finished'
            ).aggregate(
                total=Count('home_score') + Count('away_score')
            )['total'] or 0,
        }
        
        return Response(stats)


class StartTournamentView(APIView):
    """Start a tournament"""
    permission_classes = [IsAdminUserType]
    
    def post(self, request, tournament_id):
        tournament = get_object_or_404(Tournament, id=tournament_id)
        
        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut démarrer le tournoi")
        
        if tournament.status != 'upcoming':
            raise ValidationError("Seuls les tournois à venir peuvent être démarrés")
        
        # NEW: For league tournaments, auto-generate matches if none exist
        matches_generated = 0
        if tournament.tournament_type == 'league':
            existing_matches = Match.objects.filter(tournament=tournament).count()
            if existing_matches == 0:
                from .services import TournamentEngine
                engine = TournamentEngine(tournament)
                try:
                    # Enforce number_of_legs=2 for league if not set
                    if tournament.number_of_legs < 2:
                        tournament.number_of_legs = 2
                        tournament.save()
                    
                    matches = engine.generate_group_stage_matches()
                    matches_generated = len(matches)
                except Exception as e:
                    # Log error but don't stop tournament start if it's not critical
                    print(f"Error auto-generating league matches: {str(e)}")
        
        tournament.status = 'active'
        tournament.save()
        
        return Response({
            'message': 'Tournoi démarré' + (f' et {matches_generated} matchs générés' if matches_generated > 0 else ''),
            'tournament': TournamentSerializer(tournament).data,
            'matches_generated': matches_generated
        })


class FinishTournamentView(APIView):
    """Finish a tournament"""
    permission_classes = [IsAdminUserType]
    
    def post(self, request, tournament_id):
        tournament = get_object_or_404(Tournament, id=tournament_id)
        
        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut terminer le tournoi")
        
        tournament.status = 'finished'
        tournament.save()
        
        return Response({
            'message': 'Tournoi terminé',
            'tournament': TournamentSerializer(tournament).data
        })


class CancelTournamentView(APIView):
    """Cancel a tournament"""
    permission_classes = [IsAdminUserType]
    
    def post(self, request, tournament_id):
        tournament = get_object_or_404(Tournament, id=tournament_id)
        
        if tournament.organizer != request.user and not request.user.is_superuser:
            raise PermissionDenied("Seul l'organisateur peut annuler le tournoi")
        
        tournament.status = 'cancelled'
        tournament.save()
        
        return Response({
            'message': 'Tournoi annulé',
            'tournament': TournamentSerializer(tournament).data
        })


