from rest_framework import serializers
from .models import Tournament, TournamentGroup, TournamentPhase, TeamGroup, Match


class TournamentSerializer(serializers.ModelSerializer):
    """Serializer for Tournament model"""
    registered_teams_count = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)
    can_register = serializers.BooleanField(read_only=True)
    logo = serializers.ImageField(required=False, allow_null=True)
     
    class Meta:
        model = Tournament
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'organizer')
        extra_kwargs = {
            'organizer': {'read_only': True},
            'logo': {'required': False}
        }


class TeamGroupSerializer(serializers.ModelSerializer):
    """Serializer for TeamGroup model"""
    team_name = serializers.CharField(source='team.name', read_only=True)
    team_logo = serializers.SerializerMethodField()
    group_name = serializers.CharField(source='group.name', read_only=True)
    
    class Meta:
        model = TeamGroup
        fields = ['id', 'team', 'team_name', 'team_logo', 'group', 'group_name', 
                  'position', 'is_qualified', 'qualified_position', 'joined_at']
        read_only_fields = ('id', 'joined_at')

    def get_team_logo(self, obj):
        if obj.team and obj.team.club and obj.team.club.logo:
            return obj.team.club.logo.url
        return None


class AddTeamToGroupSerializer(serializers.Serializer):
    """Serializer for adding a team to a group by ID"""
    team_id = serializers.IntegerField(required=True)
    position = serializers.IntegerField(required=False, allow_null=True)
    
    def validate_team_id(self, value):
        """Check if team exists"""
        from teams.models import Team
        if not Team.objects.filter(id=value).exists():
            raise serializers.ValidationError("L'équipe n'existe pas")
        return value
    
    def validate(self, data):
        """Validate that team is not already in the group"""
        group = self.context.get('group')
        team_id = data.get('team_id')
        
        if group and TeamGroup.objects.filter(group=group, team_id=team_id).exists():
            raise serializers.ValidationError("Cette équipe est déjà dans ce groupe")
        
        return data


class TournamentGroupSerializer(serializers.ModelSerializer):
    """Serializer for TournamentGroup model"""
    teams = TeamGroupSerializer(source='team_groups', many=True, read_only=True)
    teams_count = serializers.SerializerMethodField()
    
    class Meta:
        model = TournamentGroup
        fields = ['id', 'tournament', 'name', 'description', 'order', 
                  'teams', 'teams_count', 'created_at', 'updated_at']
        read_only_fields = ('id', 'created_at', 'updated_at', 'tournament')
    
    def get_teams_count(self, obj):
        return obj.team_groups.count()


class GroupStandingsSerializer(serializers.Serializer):
    """Serializer for group standings"""
    position = serializers.IntegerField()
    team_id = serializers.UUIDField(source='team.id')
    team_name = serializers.CharField(source='team.name')
    team_logo = serializers.SerializerMethodField()
    played = serializers.IntegerField()
    wins = serializers.IntegerField()
    draws = serializers.IntegerField()
    losses = serializers.IntegerField()
    goals_scored = serializers.IntegerField()
    goals_conceded = serializers.IntegerField()
    goal_difference = serializers.IntegerField()
    points = serializers.IntegerField()
    is_qualified = serializers.BooleanField(source='team_group.is_qualified')

    def get_team_logo(self, obj):
        if obj['team'] and obj['team'].club and obj['team'].club.logo:
            return obj['team'].club.logo.url
        return None


class MatchSerializer(serializers.ModelSerializer):
    """Serializer for Match model"""
    home_team_name = serializers.CharField(source='home_team.name', read_only=True)
    away_team_name = serializers.CharField(source='away_team.name', read_only=True)
    home_team_logo = serializers.SerializerMethodField()
    away_team_logo = serializers.SerializerMethodField()
    group_name = serializers.CharField(source='group.name', read_only=True, allow_null=True)
    phase_name = serializers.CharField(source='phase.name', read_only=True, allow_null=True)
    winner_name = serializers.SerializerMethodField()
    phase_id = serializers.PrimaryKeyRelatedField(queryset=TournamentPhase.objects.all(), source='phase', write_only=True, required=False, allow_null=True)
    group_id = serializers.PrimaryKeyRelatedField(queryset=TournamentGroup.objects.all(), source='group', write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = Match
        fields = ['id', 'tournament', 'group', 'group_name', 'group_id', 'phase', 'phase_name', 'phase_id',
                  'home_team', 'home_team_name', 'home_team_logo',
                  'away_team', 'away_team_name', 'away_team_logo',
                  'match_date', 'venue', 'home_score', 'away_score',
                  'status', 'match_number', 'round_number', 'winner_name',
                  'created_at', 'updated_at']
        read_only_fields = ('id', 'created_at', 'updated_at', 'tournament')
    
    def get_home_team_logo(self, obj):
        if obj.home_team and obj.home_team.club and obj.home_team.club.logo:
            return obj.home_team.club.logo.url
        return None
    
    def get_away_team_logo(self, obj):
        if obj.away_team and obj.away_team.club and obj.away_team.club.logo:
            return obj.away_team.club.logo.url
        return None
    
    def get_winner_name(self, obj):
        winner = obj.winner
        return winner.name if winner else None


class CreateMatchSerializer(serializers.Serializer):
    """Serializer for creating a match"""
    home_team_id = serializers.IntegerField(required=True)
    away_team_id = serializers.IntegerField(required=True)
    match_date = serializers.DateTimeField(required=True)
    venue = serializers.CharField(required=False, allow_blank=True)
    round_number = serializers.IntegerField(default=1, min_value=1)
    match_number = serializers.IntegerField(required=False, allow_null=True)
    group_id = serializers.UUIDField(required=False, allow_null=True)
    phase_id = serializers.IntegerField(required=False, allow_null=True)
    
    def validate(self, data):
        """Validate match creation"""
        from teams.models import Team
        
        home_team_id = data.get('home_team_id')
        away_team_id = data.get('away_team_id')
        
        # Check teams exist
        if not Team.objects.filter(id=home_team_id).exists():
            raise serializers.ValidationError({'home_team_id': "L'équipe domicile n'existe pas"})
        
        if not Team.objects.filter(id=away_team_id).exists():
            raise serializers.ValidationError({'away_team_id': "L'équipe extérieure n'existe pas"})
        
        # Check teams are different
        if home_team_id == away_team_id:
            raise serializers.ValidationError("Une équipe ne peut pas jouer contre elle-même")
        
        # Validate teams are in the group (if group context provided)
        group = self.context.get('group')
        if group:
            home_in_group = TeamGroup.objects.filter(team_id=home_team_id, group=group).exists()
            away_in_group = TeamGroup.objects.filter(team_id=away_team_id, group=group).exists()
            
            if not home_in_group:
                raise serializers.ValidationError({'home_team_id': "L'équipe domicile n'est pas dans ce groupe"})
            
            if not away_in_group:
                raise serializers.ValidationError({'away_team_id': "L'équipe extérieure n'est pas dans ce groupe"})
        
        return data


class UpdateMatchScoreSerializer(serializers.Serializer):
    """Serializer for updating match scores"""
    home_score = serializers.IntegerField(min_value=0, required=True)
    away_score = serializers.IntegerField(min_value=0, required=True)
    status = serializers.ChoiceField(
        choices=['scheduled', 'live', 'finished', 'postponed', 'cancelled'],
        required=False
    )


class TournamentPhaseSerializer(serializers.ModelSerializer):
    """Serializer for TournamentPhase model"""
    matches_count = serializers.SerializerMethodField()
    
    class Meta:
        model = TournamentPhase
        fields = ['id', 'tournament', 'name', 'phase_type', 'order',
                  'start_date', 'end_date', 'is_active', 'is_completed',
                  'matches_count', 'created_at', 'updated_at']
        read_only_fields = ('id', 'created_at', 'updated_at')
    
    def get_matches_count(self, obj):
        return obj.matches.count()





class TournamentListSerializer(serializers.ModelSerializer):
    """Simplified serializer for tournament lists"""
    registered_teams_count = serializers.IntegerField(read_only=True)
    organizer_name = serializers.CharField(source='organizer.get_full_name', read_only=True)
    
    class Meta:
        model = Tournament
        fields = ['id', 'name', 'tournament_type', 'start_date', 'end_date', 
                  'status', 'location', 'registered_teams_count', 'max_teams',
                  'organizer_name', 'logo']


class TournamentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for tournament details"""
    groups = TournamentGroupSerializer(many=True, read_only=True)
    phases = TournamentPhaseSerializer(many=True, read_only=True)

    organizer_name = serializers.CharField(source='organizer.get_full_name', read_only=True)
    registered_teams_count = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)
    can_register = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Tournament
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'organizer')


class ComprehensiveTournamentSerializer(serializers.ModelSerializer):
    """Comprehensive serializer that includes all tournament data for caching optimization"""
    groups = TournamentGroupSerializer(many=True, read_only=True)
    phases = TournamentPhaseSerializer(many=True, read_only=True)
    matches = MatchSerializer(many=True, read_only=True, source='tournament_matches')
    
    organizer_name = serializers.CharField(source='organizer.get_full_name', read_only=True)
    registered_teams_count = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)
    can_register = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Tournament
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'organizer')
    
    def to_representation(self, instance):
        """Add standings to the representation"""
        representation = super().to_representation(instance)
        
        # Add standings for each group
        standings = []
        for group in instance.groups.all():
            group_standings = self._get_group_standings(group)
            if group_standings:
                standings.append({
                    'group_id': str(group.id),
                    'group_name': group.name,
                    'standings': group_standings
                })
        
        representation['standings'] = standings
        return representation
    
    def _get_group_standings(self, group):
        """Calculate standings for a group"""
        from django.db.models import Count, Q, Sum, F
        from teams.models import Team
        
        # Get all teams in the group with their stats
        team_groups = group.team_groups.select_related('team', 'team__club').all()
        
        standings = []
        for tg in team_groups:
            team = tg.team
            
            # Get matches for this team in this group (using correct related_name)
            home_matches = group.matches.filter(home_team=team, status='finished')
            away_matches = group.matches.filter(away_team=team, status='finished')
            
            played = home_matches.count() + away_matches.count()
            wins = 0
            draws = 0
            losses = 0
            goals_scored = 0
            goals_conceded = 0
            
            # Calculate home stats
            for match in home_matches:
                goals_scored += match.home_score or 0
                goals_conceded += match.away_score or 0
                if match.home_score > match.away_score:
                    wins += 1
                elif match.home_score == match.away_score:
                    draws += 1
                else:
                    losses += 1
            
            # Calculate away stats
            for match in away_matches:
                goals_scored += match.away_score or 0
                goals_conceded += match.home_score or 0
                if match.away_score > match.home_score:
                    wins += 1
                elif match.away_score == match.home_score:
                    draws += 1
                else:
                    losses += 1
            
            goal_difference = goals_scored - goals_conceded
            points = (wins * group.tournament.points_per_win) + (draws * group.tournament.points_per_draw) + (losses * group.tournament.points_per_loss)
            
            standings.append({
                'team_id': str(team.id),
                'team_name': team.name,
                'team_logo': team.club.logo.url if team.club and team.club.logo else None,
                'played': played,
                'wins': wins,
                'draws': draws,
                'losses': losses,
                'goals_scored': goals_scored,
                'goals_conceded': goals_conceded,
                'goal_difference': goal_difference,
                'points': points,
                'is_qualified': tg.is_qualified,
                'position': tg.position or 0
            })
        
        # Sort by points (desc), then goal difference (desc), then goals scored (desc)
        standings.sort(key=lambda x: (-x['points'], -x['goal_difference'], -x['goals_scored']))
        
        # Update positions
        for idx, standing in enumerate(standings, start=1):
            standing['position'] = idx
        
        return standings