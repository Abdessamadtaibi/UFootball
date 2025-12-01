from rest_framework import serializers
from .models import Match, MatchEvent, MatchLineup, MatchStatistics, MatchReport


class MatchSerializer(serializers.ModelSerializer):
    """Serializer for Match model"""
    home_team_name = serializers.SerializerMethodField()
    away_team_name = serializers.SerializerMethodField()
    tournament_name = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'last_updated_by')

    def get_home_team_name(self, obj):
        return getattr(obj.home_team, 'name', None)

    def get_away_team_name(self, obj):
        return getattr(obj.away_team, 'name', None)

    def get_tournament_name(self, obj):
        return getattr(obj.tournament, 'name', None)

    def get_venue(self, obj):
        return getattr(obj, 'venue_name', None)


class MatchEventSerializer(serializers.ModelSerializer):
    """Serializer for MatchEvent model"""
    team_name = serializers.SerializerMethodField()
    player_name = serializers.SerializerMethodField()
    
    class Meta:
        model = MatchEvent
        fields = '__all__'
        read_only_fields = ('created_at',)

    def get_team_name(self, obj):
        return getattr(obj.team, 'name', None)

    def get_player_name(self, obj):
        player = getattr(obj, 'player', None)
        return getattr(player, 'full_name', None) if player else None


class MatchLineupSerializer(serializers.ModelSerializer):
    """Serializer for MatchLineup model"""
    team_name = serializers.SerializerMethodField()
    player_name = serializers.SerializerMethodField()
    player_photo = serializers.SerializerMethodField()
    
    class Meta:
        model = MatchLineup
        fields = '__all__'
        read_only_fields = ('created_at',)

    def get_team_name(self, obj):
        return getattr(obj.team, 'name', None)

    def get_player_name(self, obj):
        return getattr(obj.player, 'full_name', None)

    def get_player_photo(self, obj):
        if obj.player and obj.player.photo:
            return obj.player.photo.url
        return None


class MatchStatisticsSerializer(serializers.ModelSerializer):
    """Serializer for MatchStatistics model"""
    
    class Meta:
        model = MatchStatistics
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class MatchReportSerializer(serializers.ModelSerializer):
    """Serializer for MatchReport model"""
    
    class Meta:
        model = MatchReport
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class MatchListSerializer(serializers.ModelSerializer):
    """Simplified serializer for match lists"""
    home_team_name = serializers.SerializerMethodField()
    away_team_name = serializers.SerializerMethodField()
    home_team_logo = serializers.SerializerMethodField()
    away_team_logo = serializers.SerializerMethodField()
    tournament_name = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()
    venue_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = Match
        fields = (
            'id', 'home_team', 'home_team_name', 'home_team_logo',
            'away_team', 'away_team_name', 'away_team_logo',
            'tournament', 'tournament_name', 'scheduled_date', 'status',
            'home_score', 'away_score', 'venue', 'venue_name',
            'created_by', 'last_updated_by', 'created_at', 'updated_at'
        )

    def get_home_team_name(self, obj):
        return getattr(obj.home_team, 'name', None)

    def get_away_team_name(self, obj):
        return getattr(obj.away_team, 'name', None)

    def get_home_team_logo(self, obj):
        home_team = obj.home_team
        if home_team and hasattr(home_team, 'club') and home_team.club and home_team.club.logo:
            return home_team.club.logo.url
        return None

    def get_away_team_logo(self, obj):
        away_team = obj.away_team
        if away_team and hasattr(away_team, 'club') and away_team.club and away_team.club.logo:
            return away_team.club.logo.url
        return None

    def get_tournament_name(self, obj):
        return getattr(obj.tournament, 'name', None)

    def get_venue(self, obj):
        return getattr(obj, 'venue_name', None)


class MatchDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for match details"""
    events = MatchEventSerializer(many=True, read_only=True)
    lineups = MatchLineupSerializer(many=True, read_only=True)
    statistics = MatchStatisticsSerializer(many=True, read_only=True)
    report = MatchReportSerializer(read_only=True)
    home_team_name = serializers.SerializerMethodField()
    away_team_name = serializers.SerializerMethodField()
    home_team_logo = serializers.SerializerMethodField()
    away_team_logo = serializers.SerializerMethodField()
    tournament_name = serializers.SerializerMethodField()
    venue = serializers.SerializerMethodField()
    
    class Meta:
        model = Match
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'created_by', 'last_updated_by')

    def get_home_team_name(self, obj):
        return getattr(obj.home_team, 'name', None)

    def get_away_team_name(self, obj):
        return getattr(obj.away_team, 'name', None)

    def get_tournament_name(self, obj):
        return getattr(obj.tournament, 'name', None)

    def get_venue(self, obj):
        return getattr(obj, 'venue_name', None)

    def get_home_team_logo(self, obj):
        home_team = obj.home_team
        if home_team and hasattr(home_team, 'club') and home_team.club and home_team.club.logo:
            return home_team.club.logo.url
        return None

    def get_away_team_logo(self, obj):
        away_team = obj.away_team
        if away_team and hasattr(away_team, 'club') and away_team.club and away_team.club.logo:
            return away_team.club.logo.url
        return None


class LiveMatchSerializer(serializers.ModelSerializer):
    """Serializer for live match updates"""
    recent_events = serializers.SerializerMethodField()
    current_minute = serializers.SerializerMethodField()
    
    class Meta:
        model = Match
        fields = (
            'id', 'home_team', 'away_team', 'scheduled_date', 'status',
            'home_score', 'away_score', 'current_minute', 'recent_events'
        )
        read_only_fields = ('created_at', 'updated_at')

    def get_recent_events(self, obj):
        qs = getattr(obj, 'events', None)
        if qs is None:
            return []
        events = qs.order_by('-created_at')[:5]
        return MatchEventSerializer(events, many=True).data

    def get_current_minute(self, obj):
        from datetime import datetime
        if obj.actual_start_time and obj.status in ['live', 'half_time']:
            delta = datetime.utcnow().replace(tzinfo=obj.actual_start_time.tzinfo) - obj.actual_start_time
            minutes = int(delta.total_seconds() // 60)
            return max(0, minutes)
        return 0