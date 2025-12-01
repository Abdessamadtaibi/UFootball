from django.contrib import admin
from .models import (
    Tournament, TournamentGroup, TournamentPhase, 
    TournamentNews, TeamGroup, Match
)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'tournament_type', 'status', 'start_date', 'end_date', 'location', 'organizer']
    list_filter = ['tournament_type', 'status', 'start_date', 'is_public']
    search_fields = ['id', 'name', 'location', 'organizer__email']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('id', 'name', 'description', 'tournament_type', 'logo', 'banner_image')
        }),
        ('Dates et lieu', {
            'fields': ('start_date', 'end_date', 'location', 'venue_address')
        }),
        ('Configuration', {
            'fields': ('status', 'format', 'max_teams', 'number_of_groups', 'teams_qualify_per_group')
        }),
        ('Organisateurs', {
            'fields': ('organizer', 'staff_members')
        }),
        ('Règles de jeu', {
            'fields': ('match_duration', 'half_time_duration', 'points_per_win', 'points_per_draw', 'points_per_loss')
        }),
        ('Informations supplémentaires', {
            'fields': ('rules', 'prize_description', 'registration_fee')
        }),
        ('Paramètres', {
            'fields': ('is_public', 'registration_open')
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TournamentGroup)
class TournamentGroupAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'tournament', 'order', 'teams_count', 'created_at']
    list_filter = ['tournament']
    search_fields = ['id', 'name', 'tournament__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    def teams_count(self, obj):
        return obj.team_groups.count()
    teams_count.short_description = 'Équipes'


@admin.register(TeamGroup)
class TeamGroupAdmin(admin.ModelAdmin):
    list_display = ['team', 'group', 'position', 'is_qualified', 'qualified_position', 'joined_at']
    list_filter = ['group__tournament', 'is_qualified']
    search_fields = ['team__name', 'group__name']
    readonly_fields = ['joined_at']
    
    fieldsets = (
        ('Association', {
            'fields': ('team', 'group', 'position')
        }),
        ('Qualification', {
            'fields': ('is_qualified', 'qualified_position')
        }),
        ('Métadonnées', {
            'fields': ('joined_at',)
        }),
    )


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['match_display', 'tournament', 'group', 'match_date', 'score_display', 'status']
    list_filter = ['tournament', 'status', 'match_date', 'group']
    search_fields = ['home_team__name', 'away_team__name', 'tournament__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'match_date'
    
    fieldsets = (
        ('Informations du match', {
            'fields': ('id', 'tournament', 'group', 'phase')
        }),
        ('Équipes', {
            'fields': ('home_team', 'away_team')
        }),
        ('Date et lieu', {
            'fields': ('match_date', 'venue')
        }),
        ('Scores', {
            'fields': ('home_score', 'away_score', 'status')
        }),
        ('Détails', {
            'fields': ('match_number', 'round_number')
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def match_display(self, obj):
        return f"{obj.home_team.name} vs {obj.away_team.name}"
    match_display.short_description = 'Match'
    
    def score_display(self, obj):
        return f"{obj.home_score} - {obj.away_score}"
    score_display.short_description = 'Score'

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly_fields.extend(['home_score', 'away_score'])
        return readonly_fields


@admin.register(TournamentPhase)
class TournamentPhaseAdmin(admin.ModelAdmin):
    list_display = ['name', 'tournament', 'phase_type', 'order', 'is_active', 'is_completed']
    list_filter = ['tournament', 'phase_type', 'is_active', 'is_completed']
    search_fields = ['name', 'tournament__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(TournamentNews)
class TournamentNewsAdmin(admin.ModelAdmin):
    list_display = ['title', 'tournament', 'author', 'is_important', 'is_published', 'created_at']
    list_filter = ['tournament', 'is_important', 'is_published', 'created_at']
    search_fields = ['title', 'content', 'tournament__name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Contenu', {
            'fields': ('tournament', 'title', 'content', 'author')
        }),
        ('Paramètres', {
            'fields': ('is_important', 'is_published')
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )