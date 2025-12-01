from rest_framework import serializers
from .models import Club, Team, Player


class ClubSerializer(serializers.ModelSerializer):
    """Serializer for Club model"""
    teams_count = serializers.SerializerMethodField()
    players_count = serializers.SerializerMethodField()
    # Accept 'avatar' as an alias for 'logo' on write
    avatar = serializers.ImageField(write_only=True, required=False)
    
    class Meta:
        model = Club
        fields = [
            'id', 'name', 'short_name', 'owner', 'logo', 'avatar', 'founded_year',
            'address', 'phone', 'email', 'website', 'license_number',
            'primary_color', 'secondary_color', 'is_active', 'created_at',
            'updated_at', 'teams_count', 'players_count'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']

    def to_internal_value(self, data):
        """Override to log incoming data before validation"""
        print(f"ClubSerializer.to_internal_value - Received data keys: {list(data.keys()) if hasattr(data, 'keys') else 'Not a dict'}")
        if hasattr(data, 'get'):
            avatar = data.get('avatar')
            print(f"ClubSerializer.to_internal_value - Has 'avatar': {avatar}")
            print(f"ClubSerializer.to_internal_value - Avatar type: {type(avatar)}")
            if avatar:
                print(f"ClubSerializer.to_internal_value - Avatar attributes: {dir(avatar)[:10]}")
            print(f"ClubSerializer.to_internal_value - Has 'logo': {data.get('logo')}")
        
        try:
            result = super().to_internal_value(data)
            print(f"ClubSerializer.to_internal_value - Validation SUCCESS, result keys: {list(result.keys())}")
            return result
        except Exception as e:
            print(f"ClubSerializer.to_internal_value - Validation FAILED: {str(e)}")
            print(f"ClubSerializer.to_internal_value - Error type: {type(e)}")
            raise

    def create(self, validated_data):
        # Default to active when not provided by client
        validated_data.setdefault('is_active', True)
        # Map 'avatar' -> 'logo' if provided
        if 'avatar' in validated_data:
            validated_data['logo'] = validated_data.pop('avatar')
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Map 'avatar' -> 'logo' if provided in PATCH/PUT
        print(f"ClubSerializer.update - Received validated_data keys: {list(validated_data.keys())}")
        if 'avatar' in validated_data:
            print(f"ClubSerializer.update - Mapping 'avatar' to 'logo'")
            validated_data['logo'] = validated_data.pop('avatar')
        return super().update(instance, validated_data)
    
    def get_teams_count(self, obj):
        """
        When creating, DRF may call to_representation with validated_data (a dict).
        In that case, there is no instance/ID yet, so return 0 safely.
        """
        try:
            # If `obj` is a Club instance
            if hasattr(obj, 'id') and obj.id is not None:
                return Team.objects.filter(club_id=obj.id).count()
            # If `obj` is a dict (validated_data during creation)
            if isinstance(obj, dict):
                club_id = obj.get('id')
                if club_id:
                    return Team.objects.filter(club_id=club_id).count()
                return 0
        except Exception:
            # Be defensive: never break serialization due to counts
            return 0
        return 0

    def get_players_count(self, obj):
        """
        Same defensive handling as get_teams_count for dict input during creation.
        """
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


class TeamSerializer(serializers.ModelSerializer):
    """Serializer for Team model"""
    club = ClubSerializer(read_only=True)
    club_name = serializers.CharField(source='club.name', read_only=True)
    players_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Team
        fields = [
            'id', 'name', 'club_name', 'category','club',
            'is_active', 'created_at','updated_at', 'players_count', 'coach'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at','club']

    def create(self, validated_data):
        # Default to active when not provided by client
        validated_data.setdefault('is_active', True)
        return super().create(validated_data)
    
    def get_players_count(self, obj):
        return obj.players.count()
    


class PlayerSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    age = serializers.ReadOnlyField()
    
    club_id = serializers.SerializerMethodField()
    team_name = serializers.CharField(source='team.name', read_only=True)
    
    class Meta:
        model = Player
        fields = [
            'id', 'first_name', 'last_name', 'full_name', 'birth_date', 'age',
            'team', 'team_name', 'club_id', 'jersey_number', 'position', 'is_captain', 'is_main_player',
            'height', 'weight', 'photo', 'photo_url',
            'goals_scored', 'assists', 'yellow_cards', 'red_cards', 'minutes_played',
            'parent_name', 'parent_phone', 'parent_email',
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
        
        # If updating, get the instance
        instance = self.instance
        
        if is_main_player:
            # Count current main players
            query = Player.objects.filter(
                team=team,
                is_main_player=True,
                is_active=True
            )
            
            # Exclude current instance if updating
            if instance:
                query = query.exclude(pk=instance.pk)
            
            main_players_count = query.count()
            
            if main_players_count >= 11:
                raise serializers.ValidationError({
                    'is_main_player': 'Cette équipe a déjà 11 joueurs titulaires. Vous devez d\'abord retirer un joueur titulaire.'
                })
        
        return data

