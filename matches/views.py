from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from .models import Match, MatchEvent, MatchLineup, MatchStatistics, MatchReport
from teams.models import Player, Team, Club
from .serializers import (
    MatchSerializer,
    MatchListSerializer,
    MatchDetailSerializer,
    MatchEventSerializer,
    MatchLineupSerializer,
    MatchStatisticsSerializer,
    MatchReportSerializer,
)
from users.permissions import IsAdminUserType, IsAdminOrStaffUserType, IsMatchCoachOrAdmin,IsAdminOrStaffOrParentUserType,IsStaffOrCoachUserType

    
def get_user_allowed_matches(user):
    """Helper to get allowed matches based on user role"""
    if not user or not user.is_authenticated:
        return Match.objects.none()
    
    # Admin users: see matches they created
    if user.user_type == 'admin':
        # Using created_by as per new requirement, falling back to last_updated_by if needed or just all for superuser?
        # User said "own match admin create".
        return Match.objects.filter(created_by=user).order_by('-scheduled_date')
    
    # Staff users: see matches where their club's teams play
    elif user.user_type == 'staff':
        from teams.models import Club
        
        # Get clubs owned by this user
        user_clubs = Club.objects.filter(owner=user)
        
        # Filter matches where teams from these clubs participate
        return Match.objects.filter(
            Q(home_team__club__in=user_clubs) | Q(away_team__club__in=user_clubs)
        ).distinct().order_by('-scheduled_date')
    
    # Coach users: see matches where their coached teams play
    # (Adding Coach logic explicitly as it was missing in the original get_queryset but implied by "staff/coach" in user request)
    elif getattr(user, 'user_type', '') == 'coach' or user.coached_teams.exists(): 
        # Note: user_type might not be 'coach' if they are just a user with coached_teams? 
        # The original code didn't have a specific 'coach' block in get_queryset, it just returned empty for unknown.
        # But MatchViewSet had "Staff users" and "Parent users". 
        # Let's check if 'coach' is a valid user_type or if we should check coached_teams.
        # The original code in MatchViewSet.get_queryset didn't handle 'coach' explicitly?
        # Wait, looking at the original file content...
        # It had: if user.user_type == 'admin': ... elif user.user_type == 'staff': ... elif user.user_type == 'parent': ...
        # It didn't seem to handle coaches in the list view?
        # But perform_create had logic for coaches.
        # Let's add coach support here to be safe and compliant with "staff/coach the matches creted or club team play in".
        coached_teams = user.coached_teams.all()
        if coached_teams.exists():
             return Match.objects.filter(
                Q(home_team__in=coached_teams) | Q(away_team__in=coached_teams)
            ).distinct().order_by('-scheduled_date')

    # Parent users: see matches where their player's teams play
    if user.user_type == 'parent':
        from teams.models import Team, Player
        
        # Teams followed directly
        followed_teams_ids = list(Team.objects.filter(followers=user).values_list('id', flat=True))
        
        # Teams where user is parent of a player (by email)
        if user.email:
            player_teams_ids = list(Player.objects.filter(parent_email=user.email).values_list('team_id', flat=True))
            followed_teams_ids.extend(player_teams_ids)
        
        # Unique team IDs
        team_ids = list(set(followed_teams_ids))
        
        # Filter matches where these teams play
        return Match.objects.filter(
            Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids)
        ).distinct().order_by('-scheduled_date')
    
    return Match.objects.none()


class MatchViewSet(viewsets.ModelViewSet):
    """ViewSet for managing matches with staff/coach CRUD restrictions"""
    queryset = Match.objects.all().order_by('-scheduled_date')
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MatchSerializer

    def get_permissions(self):
        # Public list/retrieve allowed
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAdminOrStaffOrParentUserType]
        else:
            # create/update/delete restricted to admin or staff users
            permission_classes = [IsAdminOrStaffUserType]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        if self.action == 'list':
            return MatchListSerializer
        if self.action == 'retrieve':
            return MatchDetailSerializer
        return MatchSerializer
    
    def get_queryset(self):
        """Filter matches based on user type"""
        return get_user_allowed_matches(self.request.user)

    def _is_coach_or_assistant(self, user, team):
        if getattr(user, 'is_admin_user', lambda: False)():
            return True
        if not team:
            return False
        if getattr(team, 'coach', None) == user:
            return True
        if hasattr(team, 'club') and getattr(team.club, 'owner', None) == user:
            return True
        assistants = getattr(team, 'assistant_coaches', None)
        try:
            return bool(assistants and user in assistants.all())
        except Exception:
            return False

    def perform_create(self, serializer):
        # Staff or coach can create matches with home_team restrictions
        user = self.request.user
        home_team = serializer.validated_data.get('home_team')
        away_team = serializer.validated_data.get('away_team')
        
        if not (home_team and away_team):
            raise PermissionDenied('home_team and away_team are required')
        
        # Check permissions based on user type
        if user.user_type == 'admin':
            raise PermissionDenied('You can only create matches in your tournaments')
        elif user.user_type == 'staff':
            # Staff: home_team must be from their club
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            if not user_clubs.filter(id=home_team.club_id).exists():
                raise PermissionDenied('You can only create matches where home_team is from your club')
        else:
            # Coach: home_team must be their coached team
            coached_teams = user.coached_teams.all()
            if home_team not in coached_teams:
                raise PermissionDenied('You can only create matches where home_team is your coached team')
        
        match = serializer.save(last_updated_by=user, created_by=user)

        # Auto-populate lineups with main players
        if home_team:
            main_players = Player.objects.filter(team=home_team, is_main_player=True, is_active=True)
            for player in main_players:
                MatchLineup.objects.create(
                    match=match,
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
                    match=match,
                    team=away_team,
                    player=player,
                    position=player.position,
                    is_starter=True,
                    minutes_played=0
                )

    def perform_update(self, serializer):
        user = self.request.user
        match = self.get_object()
        # Only the user who created the match can update it
        if match.created_by and match.created_by != user and user.user_type != 'admin':
            raise PermissionDenied('You can only update matches you created')
        serializer.save(last_updated_by=user)

    def perform_destroy(self, instance):
        user = self.request.user
        # Only the user who created the match can delete it
        if instance.created_by and instance.created_by != user and user.user_type != 'admin':
            raise PermissionDenied('You can only delete matches you created')
        instance.delete()


class MatchEventViewSet(viewsets.ModelViewSet):
    """ViewSet for managing match events"""
    queryset = MatchEvent.objects.all()
    permission_classes = [permissions.IsAuthenticated,IsStaffOrCoachUserType]
    serializer_class = MatchEventSerializer
    
    def get_queryset(self):
        """Filter match events based on user type"""
        user = self.request.user
        
        if not user or not user.is_authenticated:
            return MatchEvent.objects.none()
        
        # Staff users: events from matches where their club's teams play
        if user.user_type == 'staff':
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            return MatchEvent.objects.filter(
                Q(match__home_team__club__in=user_clubs) | Q(match__away_team__club__in=user_clubs)
            ).distinct()
        
        # Coach users: events from matches where their coached teams play
        else:
            coached_teams = user.coached_teams.all()
            return MatchEvent.objects.filter(
                Q(match__home_team__in=coached_teams) | Q(match__away_team__in=coached_teams)
            ).distinct()
    
    def perform_create(self, serializer):
        """Automatically update player stats when an event is created"""
        user = self.request.user
        team = serializer.validated_data.get('team')
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only create events for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only create events for your coached team")

        event = serializer.save(created_by=user)
        
        # Get the player's lineup entry for this match
        try:
            lineup = MatchLineup.objects.get(
                match=event.match,
                player=event.player,
                team=event.team
            )
            
            # Update stats based on event type
            if event.event_type in ['goal', 'penalty_goal']:
                lineup.goals_scored += 1
            elif event.event_type == 'yellow_card':
                lineup.yellow_cards += 1
            elif event.event_type == 'red_card':
                lineup.red_cards += 1
            
            lineup.save()
        except MatchLineup.DoesNotExist:
            # Player not in lineup, skip stats update
            pass

    def perform_update(self, serializer):
        user = self.request.user
        event = self.get_object()
        team = event.team
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only update events for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only update events for your coached team")
        
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        team = instance.team
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only delete events for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only delete events for your coached team")
        
        instance.delete()



class MatchLineupViewSet(viewsets.ModelViewSet):
    """ViewSet for managing match lineups"""
    queryset = MatchLineup.objects.all()
    permission_classes = [permissions.IsAuthenticated,IsStaffOrCoachUserType]
    serializer_class = MatchLineupSerializer
    
    def get_queryset(self):
        """Filter match lineups based on user type"""
        user = self.request.user
        
        if not user or not user.is_authenticated:
            return MatchLineup.objects.none()
        
        # Staff users: lineups from matches where their club's teams play
        if user.user_type == 'staff':
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            return MatchLineup.objects.filter(
                Q(match__home_team__club__in=user_clubs) | Q(match__away_team__club__in=user_clubs)
            ).distinct()
        
        # Coach users: lineups from matches where their coached teams play
        else:
            coached_teams = user.coached_teams.all()
            return MatchLineup.objects.filter(
                Q(match__home_team__in=coached_teams) | Q(match__away_team__in=coached_teams)
            ).distinct()

    def perform_create(self, serializer):
        user = self.request.user
        team = serializer.validated_data.get('team')
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only create lineups for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only create lineups for your coached team")
        
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        lineup = self.get_object()
        team = lineup.team
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only update lineups for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only update lineups for your coached team")
        
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        team = instance.team
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only delete lineups for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only delete lineups for your coached team")
        
        instance.delete()



class MatchStatisticsViewSet(viewsets.ModelViewSet):
    """ViewSet for managing match statistics"""
    queryset = MatchStatistics.objects.all()
    permission_classes = [permissions.IsAuthenticated,IsStaffOrCoachUserType]
    serializer_class = MatchStatisticsSerializer
    
    def get_queryset(self):
        """Filter match statistics based on user type"""
        user = self.request.user
        
        if not user or not user.is_authenticated:
            return MatchStatistics.objects.none()
        
        # Staff users: statistics from matches where their club's teams play
        if user.user_type == 'staff':
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            return MatchStatistics.objects.filter(
                Q(match__home_team__club__in=user_clubs) | Q(match__away_team__club__in=user_clubs)
            ).distinct()
        
        # Coach users: statistics from matches where their coached teams play
        else:
            coached_teams = user.coached_teams.all()
            return MatchStatistics.objects.filter(
                Q(match__home_team__in=coached_teams) | Q(match__away_team__in=coached_teams)
            ).distinct()

    def perform_create(self, serializer):
        user = self.request.user
        team = serializer.validated_data.get('team')
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only create stats for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only create stats for your coached team")
        
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        stats = self.get_object()
        team = stats.team
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only update stats for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only update stats for your coached team")
        
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        team = instance.team
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                    raise PermissionDenied("You can only delete stats for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                    raise PermissionDenied("You can only delete stats for your coached team")
        
        instance.delete()



class MatchReportViewSet(viewsets.ModelViewSet):
    """ViewSet for managing match reports"""
    queryset = MatchReport.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsStaffOrCoachUserType]
    serializer_class = MatchReportSerializer
    
    def get_queryset(self):
        """Filter match reports based on user type"""
        user = self.request.user
        
        if not user or not user.is_authenticated:
            return MatchReport.objects.none()
        
        # Staff users: reports from matches where their club's teams play
        if user.user_type == 'staff':
            from teams.models import Club
            user_clubs = Club.objects.filter(owner=user)
            return MatchReport.objects.filter(
                Q(match__home_team__club__in=user_clubs) | Q(match__away_team__club__in=user_clubs)
            ).distinct()
        
        # Coach users: reports from matches where their coached teams play
        else:
            coached_teams = user.coached_teams.all()
            return MatchReport.objects.filter(
                Q(match__home_team__in=coached_teams) | Q(match__away_team__in=coached_teams)
            ).distinct()

    def perform_create(self, serializer):
        user = self.request.user
        match = serializer.validated_data.get('match')
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(match.home_team, 'club') and match.home_team.club.owner == user):
                    raise PermissionDenied("You can only create reports for matches involving your club's team")
            else:
                if match.home_team.coach != user and match.home_team not in user.coached_teams.all():
                    raise PermissionDenied("You can only create reports for matches involving your coached team")
        
        serializer.save(author=user)

    def perform_update(self, serializer):
        user = self.request.user
        report = self.get_object()
        match = report.match
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(match.home_team, 'club') and match.home_team.club.owner == user):
                    raise PermissionDenied("You can only update reports for matches involving your club's team")
            else:
                if match.home_team.coach != user and match.home_team not in user.coached_teams.all():
                    raise PermissionDenied("You can only update reports for matches involving your coached team")
        
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        match = instance.match
        
        # Check permissions
        if user.user_type != 'admin':
            if user.user_type == 'staff':
                if not (hasattr(match.home_team, 'club') and match.home_team.club.owner == user):
                    raise PermissionDenied("You can only delete reports for matches involving your club's team")
            else:
                if match.home_team.coach != user and match.home_team not in user.coached_teams.all():
                    raise PermissionDenied("You can only delete reports for matches involving your coached team")
        
        instance.delete()



# Match management views
class StartMatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        # Check permissions: Admin or Match Creator
        user = request.user
        if user.user_type != 'admin':
            if match.created_by and match.created_by != user:
                raise PermissionDenied("You can only manage matches you created")
            if match.created_by is None:
                if user.user_type == 'staff':
                    if not (hasattr(match.home_team, 'club') and match.home_team.club.owner == user):
                        raise PermissionDenied("You can only manage matches where your club is the home team")
                else:
                    if match.home_team.coach != user and match.home_team not in user.coached_teams.all():
                        raise PermissionDenied("You can only manage matches where you are the home team coach")

        match.actual_start_time = timezone.now()
        match.status = 'live'
        match.last_updated_by = request.user
        match.save(update_fields=['actual_start_time', 'status', 'last_updated_by', 'updated_at'])
        return Response(MatchDetailSerializer(match).data, status=status.HTTP_200_OK)


class FinishMatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        # Check permissions: Admin or Match Creator
        user = request.user
        if user.user_type != 'admin':
            if match.created_by and match.created_by != user:
                raise PermissionDenied("You can only manage matches you created")
            if match.created_by is None:
                if user.user_type == 'staff':
                    if not (hasattr(match.home_team, 'club') and match.home_team.club.owner == user):
                        raise PermissionDenied("You can only manage matches where your club is the home team")
                else:
                    if match.home_team.coach != user and match.home_team not in user.coached_teams.all():
                        raise PermissionDenied("You can only manage matches where you are the home team coach")

        match.actual_end_time = timezone.now()
        match.status = 'finished'
        match.last_updated_by = request.user
        match.save(update_fields=['actual_end_time', 'status', 'last_updated_by', 'updated_at'])
        return Response(MatchDetailSerializer(match).data, status=status.HTTP_200_OK)


class PostponeMatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        # Check permissions: Admin or Match Creator
        user = request.user
        if user.user_type != 'admin':
            if match.created_by and match.created_by != user:
                raise PermissionDenied("You can only manage matches you created")
            if match.created_by is None:
                if user.user_type == 'staff':
                    if not (hasattr(match.home_team, 'club') and match.home_team.club.owner == user):
                        raise PermissionDenied("You can only manage matches where your club is the home team")
                else:
                    if match.home_team.coach != user and match.home_team not in user.coached_teams.all():
                        raise PermissionDenied("You can only manage matches where you are the home team coach")

        new_date = request.data.get('new_date')
        if not new_date:
            return Response({'detail': 'new_date is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from datetime import datetime
            match.scheduled_date = datetime.fromisoformat(new_date)
        except Exception:
            return Response({'detail': 'Invalid new_date format, use ISO 8601'}, status=status.HTTP_400_BAD_REQUEST)
        match.status = 'postponed'
        match.last_updated_by = request.user
        match.save(update_fields=['scheduled_date', 'status', 'last_updated_by', 'updated_at'])
        return Response(MatchDetailSerializer(match).data, status=status.HTTP_200_OK)


class CancelMatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        # Check permissions: Admin or Match Creator
        user = request.user
        if user.user_type != 'admin':
            if match.created_by and match.created_by != user:
                raise PermissionDenied("You can only manage matches you created")
            if match.created_by is None:
                if user.user_type == 'staff':
                    if not (hasattr(match.home_team, 'club') and match.home_team.club.owner == user):
                        raise PermissionDenied("You can only manage matches where your club is the home team")
                else:
                    if match.home_team.coach != user and match.home_team not in user.coached_teams.all():
                        raise PermissionDenied("You can only manage matches where you are the home team coach")

        match.status = 'cancelled'
        match.last_updated_by = request.user
        match.save(update_fields=['status', 'last_updated_by', 'updated_at'])
        return Response(MatchDetailSerializer(match).data, status=status.HTTP_200_OK)


class RescheduleMatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        # Check permissions: Admin or Match Creator
        user = request.user
        if user.user_type != 'admin':
            if match.created_by and match.created_by != user:
                raise PermissionDenied("You can only manage matches you created")
            if match.created_by is None:
                if user.user_type == 'staff':
                    if not (hasattr(match.home_team, 'club') and match.home_team.club.owner == user):
                        raise PermissionDenied("You can only manage matches where your club is the home team")
                else:
                    if match.home_team.coach != user and match.home_team not in user.coached_teams.all():
                        raise PermissionDenied("You can only manage matches where you are the home team coach")

        new_date = request.data.get('new_date')
        if not new_date:
            return Response({'detail': 'new_date is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from datetime import datetime
            match.scheduled_date = datetime.fromisoformat(new_date)
        except Exception:
            return Response({'detail': 'Invalid new_date format, use ISO 8601'}, status=status.HTTP_400_BAD_REQUEST)
        match.status = 'scheduled'
        match.last_updated_by = request.user
        match.save(update_fields=['scheduled_date', 'status', 'last_updated_by', 'updated_at'])
        return Response(MatchDetailSerializer(match).data, status=status.HTTP_200_OK)


# Event management views
class MatchEventsView(APIView):
    """Nested events under a match: list/create"""
    permission_classes = [IsAdminOrStaffUserType]

    def get(self, request, match_id):
        events = MatchEvent.objects.filter(match_id=match_id).order_by('minute', 'additional_time')
        return Response(MatchEventSerializer(events, many=True).data)

    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        data = request.data.copy()
        data['match'] = str(match.id)
        team_id = data.get('team')
        if not team_id:
             return Response({'detail': 'team is required'}, status=status.HTTP_400_BAD_REQUEST)
             
        # Check permissions
        user = request.user
        if user.user_type != 'admin':
            team = get_object_or_404(Team, id=team_id)
            
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                     raise PermissionDenied("You can only add events for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                     raise PermissionDenied("You can only add events for your coached team")

        # Ensure team belongs to this match
        allowed_ids = [str(match.home_team_id), str(match.away_team_id)]
        if str(team_id) not in allowed_ids:
            return Response({'detail': 'team must be home_team or away_team of this match'}, status=status.HTTP_400_BAD_REQUEST)
            
        serializer = MatchEventSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MatchEventDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, match_id, event_id):
        event = get_object_or_404(MatchEvent, id=event_id, match_id=match_id)
        
        # Check permissions
        user = request.user
        if user.user_type != 'admin':
            team = event.team
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                     raise PermissionDenied("You can only edit events for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                     raise PermissionDenied("You can only edit events for your coached team")

        serializer = MatchEventSerializer(event, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


    def delete(self, request, match_id, event_id):
        event = get_object_or_404(MatchEvent, id=event_id, match_id=match_id)
        
        # Check permissions
        user = request.user
        if user.user_type != 'admin':
            team = event.team
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                     raise PermissionDenied("You can only delete events for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                     raise PermissionDenied("You can only delete events for your coached team")
                     
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Lineup management views
class MatchLineupsView(APIView):
    """Nested lineups under a match: list/create"""
    permission_classes = [IsAdminOrStaffUserType]

    def get(self, request, match_id):
        lineups = MatchLineup.objects.filter(match_id=match_id).order_by('is_starter', 'position')
        return Response(MatchLineupSerializer(lineups, many=True).data)

    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        data = request.data.copy()
        data['match'] = str(match.id)
        team_id = data.get('team')
        if not team_id:
             return Response({'detail': 'team is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Check permissions
        user = request.user
        if user.user_type != 'admin':
            team = get_object_or_404(Team, id=team_id)
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                     raise PermissionDenied("You can only submit lineups for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                     raise PermissionDenied("You can only submit lineups for your coached team")
                     
        serializer = MatchLineupSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MatchLineupDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, match_id, lineup_id):
        lineup = get_object_or_404(MatchLineup, id=lineup_id, match_id=match_id)
        
        # Check permissions
        user = request.user
        if user.user_type != 'admin':
            team = lineup.team
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                     raise PermissionDenied("You can only edit lineups for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                     raise PermissionDenied("You can only edit lineups for your coached team")

        serializer = MatchLineupSerializer(lineup, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


    def delete(self, request, match_id, lineup_id):
        lineup = get_object_or_404(MatchLineup, id=lineup_id, match_id=match_id)
        
        # Check permissions
        user = request.user
        if user.user_type != 'admin':
            team = lineup.team
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                     raise PermissionDenied("You can only delete lineups for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                     raise PermissionDenied("You can only delete lineups for your coached team")
                     
        lineup.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class SetMatchLineupView(APIView):
    """Bulk set lineup for a team in a match"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        team_id = request.data.get('team')
        if team_id is None:
            return Response({'detail': 'team is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Check permissions
        user = request.user
        if user.user_type != 'admin':
            team = get_object_or_404(Team, id=team_id)
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                     raise PermissionDenied("You can only set lineups for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                     raise PermissionDenied("You can only set lineups for your coached team")
        # Remove existing lineups for team
        MatchLineup.objects.filter(match_id=match_id, team_id=team_id).delete()
        created = []
        for entry in starters + substitutes:
            entry_data = {
                'match': str(match.id),
                'team': team_id,
                'player': entry.get('player'),
                'position': entry.get('position'),
                'is_starter': entry in starters,
                'minutes_played': entry.get('minutes_played', 0),
            }
            serializer = MatchLineupSerializer(data=entry_data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            created.append(serializer.data)
        return Response({'lineup': created}, status=status.HTTP_200_OK)


class MatchStatsView(APIView):
    """Team aggregated stats per match"""
    permission_classes = [IsMatchCoachOrAdmin]

    def get(self, request, match_id):
        stats = MatchStatistics.objects.filter(match_id=match_id)
        return Response(MatchStatisticsSerializer(stats, many=True).data)

    def patch(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        team_id = request.data.get('team')
        if not team_id:
            return Response({'detail': 'team is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        # Check permissions
        user = request.user
        if user.user_type != 'admin':
            team = get_object_or_404(Team, id=team_id)
            if user.user_type == 'staff':
                if not (hasattr(team, 'club') and team.club.owner == user):
                     raise PermissionDenied("You can only update stats for your club's team")
            else:
                if team.coach != user and team not in user.coached_teams.all():
                     raise PermissionDenied("You can only update stats for your coached team")
                     
        stats_obj, _ = MatchStatistics.objects.get_or_create(match_id=match_id, team_id=team_id)
        serializer = MatchStatisticsSerializer(stats_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UpdatePlayerStatsView(APIView):
    """Update per-player stats for a match (minutes, goals, cards, assists)"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, match_id):
        match = get_object_or_404(Match, id=match_id)
        
        payload = request.data if isinstance(request.data, list) else request.data.get('players', [])
        if not isinstance(payload, list):
            return Response({'detail': 'Expected list of player stats or {players: [...]} payload'}, status=status.HTTP_400_BAD_REQUEST)
        updated = []
        user = request.user
        
        for item in payload:
            player_id = item.get('player')
            team_id = item.get('team')
            if not player_id or not team_id:
                return Response({'detail': 'Each item requires player and team'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Check permissions
            if user.user_type != 'admin':
                team = get_object_or_404(Team, id=team_id)
                if user.user_type == 'staff':
                    if not (hasattr(team, 'club') and team.club.owner == user):
                         raise PermissionDenied(f"You can only update stats for your club's team (Team ID: {team_id})")
                else:
                    if team.coach != user and team not in user.coached_teams.all():
                         raise PermissionDenied(f"You can only update stats for your coached team (Team ID: {team_id})")

            lineup = MatchLineup.objects.filter(match_id=match_id, player_id=player_id, team_id=team_id).first()
            if not lineup:
                return Response({'detail': f'Lineup not found for player {player_id} in match'}, status=status.HTTP_404_NOT_FOUND)
            data = {
                'minutes_played': item.get('minutes_played', lineup.minutes_played),
                'goals_scored': item.get('goals_scored', lineup.goals_scored),
                'assists': item.get('assists', lineup.assists),
                'yellow_cards': item.get('yellow_cards', lineup.yellow_cards),
                'red_cards': item.get('red_cards', lineup.red_cards),
            }
            serializer = MatchLineupSerializer(lineup, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            updated.append(serializer.data)
        return Response({'updated': updated}, status=status.HTTP_200_OK)


class PlayerStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, player_id):
        user = request.user
        
        # Check permissions
        has_access = False
        if user.user_type == 'admin':
            has_access = True
        elif user.user_type == 'staff':
            from teams.models import Club, Player
            # Check if player belongs to a team in user's club
            user_clubs = Club.objects.filter(owner=user)
            player = get_object_or_404(Player, id=player_id)
            if hasattr(player.team, 'club') and player.team.club in user_clubs:
                has_access = True
        elif getattr(user, 'user_type', '') == 'coach' or user.coached_teams.exists():
             from teams.models import Player
             player = get_object_or_404(Player, id=player_id)
             if player.team.coach == user or player.team in user.coached_teams.all():
                 has_access = True
        elif user.user_type == 'parent':
            from teams.models import Player
            # Check if user is parent of this player
            # Or if user follows the team? User request said "parent list the myplayer stats"
            # Assuming "myplayer" means their own child.
            player = get_object_or_404(Player, id=player_id)
            if player.parent_email == user.email:
                has_access = True
        
        if not has_access:
            raise PermissionDenied("You do not have permission to view this player's stats")

        # Aggregate player stats across lineups
        qs = MatchLineup.objects.filter(player_id=player_id)
        total_minutes = sum(qs.values_list('minutes_played', flat=True))
        goals = sum(qs.values_list('goals_scored', flat=True))
        assists = sum(qs.values_list('assists', flat=True))
        yellow = sum(qs.values_list('yellow_cards', flat=True))
        red = sum(qs.values_list('red_cards', flat=True))
        return Response({
            'player': player_id,
            'minutes_played': total_minutes,
            'goals_scored': goals,
            'assists': assists,
            'yellow_cards': yellow,
            'red_cards': red,
        })




# Report management views



# Public views (now restricted)



class UpcomingMatchesView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        qs = get_user_allowed_matches(request.user)
        
        team_id = request.query_params.get('team')
        days = int(request.query_params.get('days', '30'))
        now = timezone.now()
        from datetime import timedelta
        end_date = now + timedelta(days=days)
        
        qs = qs.filter(scheduled_date__gte=now, scheduled_date__lte=end_date).exclude(status__in=['cancelled']).order_by('scheduled_date')
        if team_id:
            qs = qs.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))
        return Response(MatchListSerializer(qs, many=True).data)


class LiveMatchesView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        qs = get_user_allowed_matches(request.user)
        qs = qs.filter(status__in=['live', 'half_time']).order_by('scheduled_date')
        return Response(MatchListSerializer(qs, many=True).data)


class RecentMatchesView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        qs = get_user_allowed_matches(request.user)
        
        team_id = request.query_params.get('team')
        days = int(request.query_params.get('days', '30'))
        now = timezone.now()
        from datetime import timedelta
        start_date = now - timedelta(days=days)
        
        qs = qs.filter(scheduled_date__lte=now, scheduled_date__gte=start_date, status__in=['finished', 'cancelled', 'postponed']).order_by('-scheduled_date')
        if team_id:
            qs = qs.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))
        return Response(MatchListSerializer(qs, many=True).data)


# Calendar and schedule views



class TeamScheduleView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, team_id):
        qs = get_user_allowed_matches(request.user)
        qs = qs.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id)).order_by('scheduled_date')
        return Response(MatchListSerializer(qs, many=True).data)


class TournamentScheduleView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, tournament_id):
        qs = get_user_allowed_matches(request.user)
        qs = qs.filter(tournament_id=tournament_id).order_by('scheduled_date')
        return Response(MatchListSerializer(qs, many=True).data)


# Search and filter views
class SearchMatchesView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        qs = get_user_allowed_matches(request.user)
        q = request.query_params.get('q', '')
        qs = qs.filter(
            Q(home_team__name__icontains=q) |
            Q(away_team__name__icontains=q) |
            Q(venue_name__icontains=q)
        ).order_by('-scheduled_date')
        return Response(MatchListSerializer(qs, many=True).data)


class FilterMatchesView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        qs = get_user_allowed_matches(request.user)
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return Response(MatchListSerializer(qs.order_by('-scheduled_date'), many=True).data)
