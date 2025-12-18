from rest_framework.exceptions import PermissionDenied
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg
from .models import Club, Team, Player
from .serializers import (
    ClubSerializer, TeamSerializer, PlayerSerializer
)
from users.permissions import IsAdminOrStaffUserType,IsStaffUserType,IsAdminOrStaffOrParentUserType

 
class ClubViewSet(viewsets.ModelViewSet):
    """ViewSet for managing clubs"""
    queryset = Club.objects.all()
    serializer_class = ClubSerializer
    permission_classes = [IsAdminOrStaffOrParentUserType]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAdminOrStaffOrParentUserType]
        else:
            # Restrict create/update/delete to admin or staff user types
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

class TeamViewSet(viewsets.ModelViewSet):
    
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [IsAdminOrStaffOrParentUserType]
    
    def get_queryset(self):
        # Filter teams by club_id from URL
        club_id = self.kwargs.get('club_pk')
        if club_id:
            return Team.objects.filter(club_id=club_id)
        return Team.objects.all()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAdminOrStaffOrParentUserType]
        else:
            permission_classes = [permissions.IsAuthenticated,IsStaffUserType]
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
    permission_classes = [permissions.IsAuthenticated,IsAdminOrStaffOrParentUserType]

    def get_queryset(self):
        user = self.request.user
        return Team.objects.filter(
            Q(club__owner=user) | 
            Q(coach=user) |
            Q(followers=user)
        ).distinct()

class MyPlayersView(ListAPIView):
    serializer_class = PlayerSerializer
    permission_classes = [permissions.IsAuthenticated,IsAdminOrStaffOrParentUserType]

    def get_queryset(self):
        user = self.request.user
        queryset = Player.objects.filter(
            Q(team__followers=user) |
            Q(parent_email=user.email) |
            Q(parent2_email=user.email)
        ).distinct()
        
        return queryset

        
class PlayerViewSet(viewsets.ModelViewSet):
    queryset = Player.objects.all()
    serializer_class = PlayerSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Respect nested router params and optional query filters
        queryset = Player.objects.all()

        # Prefer team_pk from nested route: /clubs/<club_pk>/teams/<team_pk>/players/
        team_id = self.kwargs.get('team_pk') or self.request.query_params.get('team_id')
        is_main = self.request.query_params.get('is_main_player')

        if team_id:
            queryset = queryset.filter(team_id=team_id)

        if is_main is not None:
            val = str(is_main).lower()
            queryset = queryset.filter(is_main_player=(val == 'true' or val == '1'))

        return queryset
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAdminOrStaffOrParentUserType]
        else:
            permission_classes = [permissions.IsAuthenticated, IsStaffUserType]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        team_id = self.kwargs.get('team_pk')
        team = get_object_or_404(Team,pk=team_id)
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
        # Support nested routes: prefer team_pk from URL, fallback to query param
        team_id = kwargs.get('team_pk') or request.query_params.get('team_id')

        if not team_id:
            return Response(
                {'error': 'team_id (or team_pk in URL) is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        team = get_object_or_404(Team, id=team_id)
        main_players = team.players.filter(is_main_player=True, is_active=True)
        
        serializer = self.get_serializer(main_players, many=True)
        return Response({
            'team': team.name,
            'count': main_players.count(),
            'max_allowed': 11,
            'players': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def substitute_players(self, request, *args, **kwargs):
        """Get all substitute players for a team"""
        # Support nested routes: prefer team_pk from URL, fallback to query param
        team_id = kwargs.get('team_pk') or request.query_params.get('team_id')

        if not team_id:
            return Response(
                {'error': 'team_id (or team_pk in URL) is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        team = get_object_or_404(Team, id=team_id)
        substitute_players = team.players.filter(is_main_player=False, is_active=True)
        
        serializer = self.get_serializer(substitute_players, many=True)
        return Response({
            'team': team.name,
            'count': substitute_players.count(),
            'players': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def set_as_main(self, request, pk=None, *args, **kwargs):
        """Set a player as main player"""
        player = self.get_object()
        
        # Check permissions
        if player.team.club.owner != request.user and player.team.coach != request.user:
            raise PermissionDenied({'error': 'Only the owner or the coach can modify main players'})
        
        # Check if team already has 11 main players
        main_players_count = Player.objects.filter(
            team=player.team,
            is_main_player=True,
            is_active=True
        ).exclude(pk=player.pk).count()
        
        if main_players_count >= 11:
            return Response(
                {'error': 'Cette équipe a déjà 11 joueurs titulaires'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        player.is_main_player = True
        player.save()
        
        serializer = self.get_serializer(player)
        return Response({
            'message': f'{player.full_name} est maintenant joueur titulaire',
            'player': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def remove_as_main(self, request, pk=None, *args, **kwargs):
        """Remove a player from main players"""
        player = self.get_object()
        
        # Check permissions
        if player.team.club.owner != request.user and player.team.coach != request.user:
            raise PermissionDenied({'error': 'Only the owner or the coach can modify main players'})
        
        player.is_main_player = False
        player.save()
        
        serializer = self.get_serializer(player)
        return Response({
            'message': f'{player.full_name} n\'est plus joueur titulaire',
            'player': serializer.data
        })


class PublicTeamViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for public team access"""
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated,IsAdminOrStaffOrParentUserType]
    pagination_class = None
    
    def get_queryset(self):
        queryset = Team.objects.all()
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    @action(detail=True, methods=['get'])
    def players(self, request, pk=None):
        """Get all players for a specific team (public access)"""
        team = self.get_object()
        players = Player.objects.filter(team=team, is_active=True)
        serializer = PlayerSerializer(players, many=True)
        return Response({'results': serializer.data})
