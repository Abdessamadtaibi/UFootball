from django.contrib import admin
from django.utils.html import format_html
from .models import Match, MatchEvent, MatchLineup, MatchStatistics, MatchReport


class MatchEventInline(admin.TabularInline):
    model = MatchEvent
    extra = 0
    fields = ('minute', 'event_type', 'team', 'player', 'description')
    ordering = ('minute',)


class MatchLineupInline(admin.TabularInline):
    model = MatchLineup
    extra = 0
    fields = ('team', 'player', 'position', 'is_starter', 'is_captain')
    ordering = ('is_starter', 'position')


class MatchStatisticsInline(admin.StackedInline):
    model = MatchStatistics
    extra = 0
    fields = (
        ('shots_total', 'shots_on_target', 'shots_off_target', 'shots_blocked'),
        ('possession_percentage', 'passes_completed', 'passes_total'),
        ('corners', 'fouls_committed', 'yellow_cards', 'red_cards')
    )


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'match_display', 'tournament', 'scheduled_date', 'status', 'score_display', 'venue_name')
    list_filter = ('status', 'tournament', 'scheduled_date', 'venue_name')
    search_fields = ('home_team__name', 'away_team__name', 'tournament__name', 'venue_name')
    ordering = ('-scheduled_date',)
    date_hierarchy = 'scheduled_date'
    
    fieldsets = (
        ('Identifiants', {
            'fields': ('id',),
        }),
        ('Informations générales', {
            'fields': ('tournament', 'phase', 'group')
        }),
        ('Équipes', {
            'fields': ('home_team', 'away_team')
        }),
        ('Date et lieu', {
            'fields': ('scheduled_date', 'venue_name', 'field_number')
        }),
        ('Résultat', {
            'fields': ('home_score', 'away_score', 'status')
        }),
        ('Arbitrage', {
            'fields': ('referee', 'assistant_referee_1', 'assistant_referee_2'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [MatchLineupInline, MatchEventInline, MatchStatisticsInline]
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    def match_display(self, obj):
        return f"{obj.home_team.name} vs {obj.away_team.name}"
    match_display.short_description = 'Match'
    
    def score_display(self, obj):
        if obj.status in ['finished', 'abandoned']:
            return f"{obj.home_score} - {obj.away_score}"
        return 'N/A'
    score_display.short_description = 'Score'

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly_fields.extend([
                'home_score', 'away_score', 
                'home_score_half_time', 'away_score_half_time',
                'home_score_extra_time', 'away_score_extra_time',
                'home_score_penalties', 'away_score_penalties'
            ])
        return readonly_fields


@admin.register(MatchEvent)
class MatchEventAdmin(admin.ModelAdmin):
    list_display = ('match_display', 'minute', 'event_type', 'player', 'team')
    list_filter = ('event_type', 'match__tournament', 'match__scheduled_date')
    search_fields = ('match__home_team__name', 'match__away_team__name', 'player__first_name', 'player__last_name')
    ordering = ('match', 'minute')
    
    fieldsets = (
        ('Match', {
            'fields': ('match',)
        }),
        ('Événement', {
            'fields': ('minute', 'event_type', 'player', 'description')
        }),
    )
    
    readonly_fields = ('created_at',)
    
    def match_display(self, obj):
        return f"{obj.match.home_team.name} vs {obj.match.away_team.name}"
    match_display.short_description = 'Match'
    
    def team(self, obj):
        if obj.player:
            return obj.player.team.name
        return 'N/A'
    team.short_description = 'Équipe'


@admin.register(MatchLineup)
class MatchLineupAdmin(admin.ModelAdmin):
    list_display = ('match_display', 'player', 'team', 'position', 'is_starter', 'is_captain')
    list_filter = ('is_starter', 'is_captain', 'position', 'match__tournament')
    search_fields = ('match__home_team__name', 'match__away_team__name', 'player__first_name', 'player__last_name')
    ordering = ('match', 'team', 'is_starter', 'position')
    
    fieldsets = (
        ('Match', {
            'fields': ('match', 'team')
        }),
        ('Joueur', {
            'fields': ('player', 'position', 'is_starter', 'is_captain')
        }),
    )
    
    def match_display(self, obj):
        return f"{obj.match.home_team.name} vs {obj.match.away_team.name}"
    match_display.short_description = 'Match'


@admin.register(MatchStatistics)
class MatchStatisticsAdmin(admin.ModelAdmin):
    list_display = ('match_display', 'team', 'shots_total', 'possession_percentage', 'shots_on_target')
    list_filter = ('match__tournament', 'match__scheduled_date')
    search_fields = ('match__home_team__name', 'match__away_team__name', 'team__name')
    ordering = ('match', 'team')
    
    fieldsets = (
        ('Match', {
            'fields': ('match', 'team')
        }),
        ('Tirs', {
            'fields': ('shots_total', 'shots_on_target', 'shots_off_target', 'shots_blocked')
        }),
        ('Possession et passes', {
            'fields': ('possession_percentage', 'passes_completed', 'passes_total')
        }),
        ('Discipline', {
            'fields': ('corners', 'fouls_committed', 'yellow_cards', 'red_cards')
        }),
    )
    
    def match_display(self, obj):
        return f"{obj.match.home_team.name} vs {obj.match.away_team.name}"
    match_display.short_description = 'Match'


@admin.register(MatchReport)
class MatchReportAdmin(admin.ModelAdmin):
    list_display = ('match_display', 'author', 'is_validated', 'created_at')
    list_filter = ('is_validated', 'match__tournament', 'created_at')
    search_fields = ('match__home_team__name', 'match__away_team__name', 'summary')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Match', {
            'fields': ('match',)
        }),
        ('Rapport', {
            'fields': ('summary', 'key_moments', 'is_validated')
        }),
        ('Validation', {
            'fields': ('author', 'validated_by'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    def match_display(self, obj):
        return f"{obj.match.home_team.name} vs {obj.match.away_team.name}"
    match_display.short_description = 'Match'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Si c'est une création
            obj.author = request.user
        super().save_model(request, obj, form, change)
