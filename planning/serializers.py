from rest_framework import serializers
from .models import TrainingSession, Event, Convocation


class TrainingSessionSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source='team.name', read_only=True)
    coach_name = serializers.CharField(source='coach.full_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    season_name = serializers.CharField(source='season.name', read_only=True)

    class Meta:
        model = TrainingSession
        fields = [
            'id', 'team', 'team_name', 'category', 'category_name',
            'coach', 'coach_name', 'season', 'season_name',
            'date', 'start_time', 'end_time', 'location',
            'title', 'notes', 'is_cancelled', 'cancellation_reason',
            'recurrence', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'team', 'created_at', 'updated_at']

    def validate(self, data):
        """Validate start_time < end_time and no overlap."""
        start_time = data.get('start_time', getattr(self.instance, 'start_time', None))
        end_time = data.get('end_time', getattr(self.instance, 'end_time', None))
        date = data.get('date', getattr(self.instance, 'date', None))
        team = data.get('team', getattr(self.instance, 'team', None))

        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({
                'end_time': "L'heure de fin doit être après l'heure de début."
            })

        # Check overlap
        if team and date and start_time and end_time:
            overlapping = TrainingSession.objects.filter(
                team=team,
                date=date,
                start_time__lt=end_time,
                end_time__gt=start_time,
            )
            if self.instance:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            if overlapping.exists():
                raise serializers.ValidationError(
                    "Une séance d'entraînement existe déjà à ce créneau horaire pour cette équipe."
                )

        return data


class ConvocationSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source='player.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Convocation
        fields = [
            'id','player', 'player_name', 'status', 'status_display',
            'notified', 'notified_at', 'parent_response_at'
        ]
        read_only_fields = ['id','player_name','updated_at']


class EventSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source='team.name', read_only=True)
    season_name = serializers.CharField(source='season.name', read_only=True)
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    convocations = ConvocationSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            'id', 'team', 'team_name', 'season', 'season_name',
            'event_type', 'event_type_display',
            'title', 'opponent', 'location',
            'date', 'start_time', 'end_time',
            'status', 'status_display',
            'notes', 'created_at', 'updated_at',
            'convocations',
        ]
        read_only_fields = ['id', 'team', 'created_at', 'updated_at']

    def validate(self, data):
        """Validate start_time < end_time and no overlap."""
        start_time = data.get('start_time', getattr(self.instance, 'start_time', None))
        end_time = data.get('end_time', getattr(self.instance, 'end_time', None))
        date = data.get('date', getattr(self.instance, 'date', None))
        team = data.get('team', getattr(self.instance, 'team', None))

        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({
                'end_time': "L'heure de fin doit être après l'heure de début."
            })

        # Check overlap
        if team and date and start_time:
            if end_time:
                overlapping = Event.objects.filter(
                    team=team, date=date,
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                )
            else:
                overlapping = Event.objects.filter(
                    team=team, date=date,
                    start_time=start_time,
                )
            if self.instance:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            if overlapping.exists():
                raise serializers.ValidationError(
                    "Un événement existe déjà à ce créneau horaire pour cette équipe."
                )

        return data
