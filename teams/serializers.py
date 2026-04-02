from rest_framework import serializers
from .models import (
    Club, Team, Player, Season, Category, Coach,
    SeasonTeamStats, SeasonPlayerStats, SeasonTournamentResult,
    SeasonPlayerRoster,
)


# ─────────────────────────────────────────────
# Season Stats Serializers
# ─────────────────────────────────────────────

class SeasonTeamStatsSerializer(serializers.ModelSerializer):
    goal_difference = serializers.ReadOnlyField()
    points = serializers.ReadOnlyField()
    win_rate = serializers.ReadOnlyField()

    class Meta:
        model = SeasonTeamStats
        fields = [
            'id', 'matches_played', 'matches_won', 'matches_drawn', 'matches_lost',
            'goals_for', 'goals_against', 'goal_difference', 'points', 'win_rate',
            'clean_sheets', 'yellow_cards', 'red_cards',
            'trophies_won', 'best_finish', 'updated_at',
        ]
        read_only_fields = fields


class SeasonPlayerStatsSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source='player.full_name', read_only=True)
    jersey_number = serializers.IntegerField(source='player.jersey_number', read_only=True)
    position = serializers.CharField(source='player.position', read_only=True)

    class Meta:
        model = SeasonPlayerStats
        fields = [
            'id', 'player', 'player_name', 'jersey_number', 'position',
            'matches_played', 'matches_started', 'minutes_played',
            'goals_scored', 'assists', 'yellow_cards', 'red_cards',
            'average_rating', 'updated_at',
        ]
        read_only_fields = fields


class SeasonPlayerRosterSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = SeasonPlayerRoster
        fields = [
            'id', 'player', 'first_name', 'last_name', 'full_name',
            'birth_date', 'jersey_number', 'position',
            'is_captain', 'is_main_player', 'status', 'created_at',
        ]
        read_only_fields = fields


class SeasonTournamentResultSerializer(serializers.ModelSerializer):
    tournament_name = serializers.CharField(source='tournament.name', read_only=True)
    goal_difference = serializers.ReadOnlyField()

    class Meta:
        model = SeasonTournamentResult
        fields = [
            'id', 'tournament', 'tournament_name',
            'final_position', 'group_name', 'group_position',
            'points', 'matches_played', 'matches_won', 'matches_drawn', 'matches_lost',
            'goals_for', 'goals_against', 'goal_difference',
            'is_champion', 'trophy_name', 'updated_at',
        ]
        read_only_fields = fields


# ─────────────────────────────────────────────
# Season (with nested stats + roster)
# ─────────────────────────────────────────────

class SeasonSerializer(serializers.ModelSerializer):
    team_stats = SeasonTeamStatsSerializer(read_only=True)
    player_stats = SeasonPlayerStatsSerializer(many=True, read_only=True)
    player_roster = SeasonPlayerRosterSerializer(many=True, read_only=True)
    tournament_results = SeasonTournamentResultSerializer(many=True, read_only=True)

    class Meta:
        model = Season
        fields = [
            'id', 'name', 'team', 'start_date', 'end_date', 'is_active',
            'created_at', 'updated_at',
            'team_stats', 'player_stats', 'player_roster', 'tournament_results',
        ]
        read_only_fields = fields


# ─────────────────────────────────────────────
# Category
# ─────────────────────────────────────────────

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'club', 'description', 'min_age', 'max_age', 'order', 'created_at']
        read_only_fields = ['id', 'created_at']


# ─────────────────────────────────────────────
# Club
# ─────────────────────────────────────────────

class ClubSerializer(serializers.ModelSerializer):
    """Serializer for Club model"""
    teams_count = serializers.SerializerMethodField()
    players_count = serializers.SerializerMethodField()
    # Accept 'avatar' as an alias for 'logo' on write
    avatar = serializers.ImageField(write_only=True, required=False)
    categories = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Club
        fields = [
            'id', 'name', 'short_name', 'owner', 'logo', 'avatar', 'founded_year',
            'discipline',
            'address', 'city', 'phone', 'email', 'website', 'license_number',
            'primary_color', 'secondary_color', 'is_active',
            'categories',
            'created_at', 'updated_at', 'teams_count', 'players_count'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']

    def to_internal_value(self, data):
        result = super().to_internal_value(data)
        return result

    def create(self, validated_data):
        validated_data.setdefault('is_active', True)
        if 'avatar' in validated_data:
            validated_data['logo'] = validated_data.pop('avatar')
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'avatar' in validated_data:
            validated_data['logo'] = validated_data.pop('avatar')
        return super().update(instance, validated_data)

    def get_teams_count(self, obj):
        try:
            if hasattr(obj, 'id') and obj.id is not None:
                return Team.objects.filter(club_id=obj.id).count()
            if isinstance(obj, dict):
                club_id = obj.get('id')
                if club_id:
                    return Team.objects.filter(club_id=club_id).count()
                return 0
        except Exception:
            return 0
        return 0

    def get_players_count(self, obj):
        try:
            if hasattr(obj, 'id') and obj.id is not None:
                return Player.objects.filter(team__club_id=obj.id).count()
            if isinstance(obj, dict):
                club_id = obj.get('id')
                if club_id:
                    return Player.objects.filter(team__club_id=club_id).count()
                return 0
        except Exception:
            return 0
        return 0


# ─────────────────────────────────────────────
# Team
# ─────────────────────────────────────────────

class TeamSerializer(serializers.ModelSerializer):
    """Serializer for Team model"""
    club_name = serializers.CharField(source='club.name', read_only=True)
    players_count = serializers.SerializerMethodField()
    category_obj_name = serializers.CharField(source='category_obj.name', read_only=True)
    season_name = serializers.CharField(source='season.name', read_only=True)
    sport_display = serializers.CharField(source='get_sport_display', read_only=True)

    class Meta:
        model = Team
        fields = [
            'id', 'name', 'club', 'club_name', 'category', 'category_obj', 'category_obj_name',
            'sport', 'sport_display', 'season', 'season_name',
            'is_active', 'created_at', 'updated_at', 'players_count', 'coach',
            'default_venue'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'club']

    def create(self, validated_data):
        validated_data.setdefault('is_active', True)
        return super().create(validated_data)

    def get_players_count(self, obj):
        return obj.players.count()


# ─────────────────────────────────────────────
# Player
# ─────────────────────────────────────────────

class PlayerSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    age = serializers.ReadOnlyField()

    club_id = serializers.SerializerMethodField()
    team_name = serializers.CharField(source='team.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Player
        fields = [
            # Identité
            'id', 'first_name', 'last_name', 'full_name', 'birth_date', 'age',
            'birth_place', 'nationality', 'photo', 'photo_url',
            # Coordonnées
            'address', 'city',
            # Responsables légaux
            'father_name', 'father_phone', 'father_email',
            'mother_name', 'mother_phone', 'mother_email',
            # Médical
            'blood_type', 'allergies', 'medical_authorization', 'treating_doctor',
            'height', 'weight',
            # Autorisations
            'parental_authorization', 'transport_authorization',
            'image_authorization', 'digital_signature',
            # Sportif
            'team', 'team_name', 'club_id', 'category', 'category_name',
            'jersey_number', 'position', 'is_captain', 'is_main_player',
            'enrollment_date', 'status',
            # Stats
            'goals_scored', 'assists', 'yellow_cards', 'red_cards', 'minutes_played',
            # Meta
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_club_id(self, obj):
        return obj.team.club.id if obj.team and obj.team.club else None

    def get_photo_url(self, obj):
        if obj.photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.photo.url)
        return None

    def get_full_name(self, obj):
        return obj.full_name

    def validate(self, data):
        """Validate that team doesn't exceed 11 main players"""
        is_main_player = data.get('is_main_player', False)
        team = data.get('team')
        instance = self.instance

        if is_main_player and team:
            query = Player.objects.filter(
                team=team,
                is_main_player=True,
                is_active=True
            )
            if instance:
                query = query.exclude(pk=instance.pk)
            if query.count() >= 11:
                raise serializers.ValidationError({
                    'is_main_player': "Cette équipe a déjà 11 joueurs titulaires."
                })
        return data


# ─────────────────────────────────────────────
# Coach
# ─────────────────────────────────────────────

class CoachSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    supervised_category_names = serializers.SerializerMethodField()
    # Make these fields optional as they will be fetched from the User model if missing
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)

    class Meta:
        model = Coach
        fields = [
            'id', 'user', 'team',
            'first_name', 'last_name', 'full_name',
            'birth_date', 'nationality', 'photo',
            'phone', 'email', 'address',
            'diplomas', 'certifications', 'license_level',
            'experience_years', 'specialization',
            'supervised_categories', 'supervised_category_names',
            'availabilities',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'team', 'created_at', 'updated_at']

    def get_supervised_category_names(self, obj):
        return [cat.name for cat in obj.supervised_categories.all()]

    def validate_user(self, value):
        """Check if the user is a coach and doesn't already have a profile."""
        if value.user_type != 'coach':
            raise serializers.ValidationError("L'utilisateur spécifié doit avoir le type 'coach'.")
        
        # If we are creating (no instance), check if profile already exists
        if not self.instance:
            if hasattr(value, 'coach_profile'):
                raise serializers.ValidationError("Cet utilisateur a déjà un profil coach.")
        else:
            # If we are updating, check if the other profile belongs to someone else
            if hasattr(value, 'coach_profile') and value.coach_profile.pk != self.instance.pk:
                raise serializers.ValidationError("Cet utilisateur est déjà associé à un autre profil coach.")
                
        return value

    def validate(self, data):
        """Automatically populate first_name, last_name, and email from User if missing."""
        user = data.get('user')
        if user:
            if not data.get('first_name'):
                data['first_name'] = user.first_name
            if not data.get('last_name'):
                data['last_name'] = user.last_name
            if not data.get('email'):
                data['email'] = user.email
        
        # Ensure mandatory model fields are always present even if missed in request
        if not data.get('first_name') or not data.get('last_name') or not data.get('email'):
             raise serializers.ValidationError("Prénom, nom et email sont requis (extraits de l'utilisateur ou fournis).")
             
        return data
