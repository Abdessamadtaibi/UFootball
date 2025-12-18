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
from users.permissions import IsAdminUserType, IsAdminActiveUserType, IsOrganizerOrSuperUser, IsMatchCoachOrAdmin, IsAdminOrStaffOrParentUserType, IsViewerOrAdminOrStaffOrParentUserType


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
                    Q(parent_email=user.email) | Q(parent2_email=user.email)
                ).values_list('team_id', flat=True))
                followed_teams_ids.extend(player_teams_ids)
            
            # Unique team IDs
            team_ids = list(set(followed_teams_ids))
            
            queryset = Tournament.objects.filter(
                Q(teamtournamentregistration__team_id__in=team_ids) |
                Q(groups__team_groups__team_id__in=team_ids)
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
                    Q(parent_email=request.user.email) | Q(parent2_email=request.user.email)
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
                    Q(parent_email=user.email) | Q(parent2_email=user.email)
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
            queryset = queryset.filter(status=match_status)
            
        # Add team filter
        team_id = self.request.query_params.get('team')
        if team_id:
            queryset = queryset.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))
        
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
        """Finish a match"""
        match = self.get_object()
        tournament = match.tournament
        
        perm = IsMatchCoachOrAdmin()
        is_organizer = tournament.organizer == request.user or request.user.is_superuser
        
        if not is_organizer and not perm.has_object_permission(request, self, match):
            raise PermissionDenied("Seul l'organisateur ou les coachs peuvent terminer les matchs")
        
        if match.status not in ['live', 'scheduled']:
            raise ValidationError("Le match doit être en cours ou programmé")
        
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
                    Q(parent_email=user.email) | Q(parent2_email=user.email)
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
                    Q(parent_email=user.email) | Q(parent2_email=user.email)
                ).values_list('team_id', flat=True))
                followed_teams_ids.extend(player_teams_ids)
            has_access = tournament.teamtournamentregistration_set.filter(team_id__in=followed_teams_ids).exists() or \
                         tournament.groups.filter(team_groups__team_id__in=followed_teams_ids).exists()
            if not has_access:
                raise PermissionDenied("Accès restreint aux tournois de vos équipes")
        
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
        
        return Response(standings_data)


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
                    Q(parent_email=user.email) | Q(parent2_email=user.email)
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
        
        tournament.status = 'active'
        tournament.save()
        
        return Response({
            'message': 'Tournoi démarré',
            'tournament': TournamentSerializer(tournament).data
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


