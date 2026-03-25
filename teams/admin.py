from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Club, Team, Player, TeamTournamentRegistration, TeamStaff,
    Season, Category, Coach,
    SeasonTeamStats, SeasonPlayerStats, SeasonTournamentResult,
)


# ─────────────────────────────────────────────
# Season
# ─────────────────────────────────────────────

@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'team', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'team')
    search_fields = ('name', 'team__name')
    ordering = ('-start_date',)


# ─────────────────────────────────────────────
# Category
# ─────────────────────────────────────────────

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'club', 'min_age', 'max_age', 'order')
    list_filter = ('club',)
    search_fields = ('name', 'club__name')
    ordering = ('club', 'order', 'name')


# ─────────────────────────────────────────────
# Coach
# ─────────────────────────────────────────────

@admin.register(Coach)
class CoachAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'team', 'license_level', 'experience_years', 'is_active')
    list_filter = ('is_active', 'team')
    search_fields = ('first_name', 'last_name', 'email', 'team__name')
    ordering = ('last_name', 'first_name')
    filter_horizontal = ('supervised_categories',)

    fieldsets = (
        ('Identité', {
            'fields': ('user', 'team', 'first_name', 'last_name', 'birth_date', 'nationality', 'photo')
        }),
        ('Contact', {
            'fields': ('phone', 'email', 'address')
        }),
        ('Qualifications', {
            'fields': ('diplomas', 'certifications', 'license_level', 'experience_years', 'specialization'),
            'classes': ('collapse',)
        }),
        ('Encadrement', {
            'fields': ('supervised_categories', 'availabilities'),
            'classes': ('collapse',)
        }),
        ('Statut', {
            'fields': ('is_active',)
        }),
    )
    readonly_fields = ('created_at',)

# ─────────────────────────────────────────────
# Club
# ─────────────────────────────────────────────

@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'short_name', 'discipline', 'city', 'founded_year', 'teams_count', 'is_active')
    list_filter = ('is_active', 'founded_year')
    search_fields = ('id', 'name', 'short_name', 'address', 'city')
    ordering = ('name',)

    fieldsets = (
        ('Informations générales', {
            'fields': ('name', 'short_name', 'owner', 'logo', 'is_active')
        }),
        ('Discipline', {
            'fields': ('discipline',)
        }),
        ('Localisation', {
            'fields': ('address', 'city', 'phone', 'email', 'website')
        }),
        ('Apparence', {
            'fields': ('primary_color', 'secondary_color'),
            'classes': ('collapse',)
        }),
        ('Historique', {
            'fields': ('founded_year', 'license_number')
        }),
        ('Métadonnées', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('id', 'created_at')

    def get_changeform_initial_data(self, request):
        return {'is_active': True}

    def teams_count(self, obj):
        return obj.teams.count()
    teams_count.short_description = "Nombre d'équipes"


# ─────────────────────────────────────────────
# Team
# ─────────────────────────────────────────────

class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0
    fields = ('jersey_number', 'first_name', 'last_name', 'position', 'birth_date', 'status', 'is_active')
    readonly_fields = ('created_at',)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        try:
            formset.form.base_fields['is_active'].initial = True
        except Exception:
            pass
        return formset


class TeamStaffInline(admin.TabularInline):
    model = TeamStaff
    extra = 0
    fields = ('user', 'role', 'is_active')


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'club', 'coach_name', 'category', 'players_count', 'season', 'is_active')
    list_filter = ('is_active', 'category', 'club', 'season')
    search_fields = ('id', 'name', 'club__name', 'coach__first_name', 'coach__last_name')
    ordering = ('club', 'name')

    fieldsets = (
        ('Informations générales', {
            'fields': ('club', 'name', 'category', 'sport', 'category_obj', 'season', 'is_active')
        }),
        ('Encadrement', {
            'fields': ('coach', 'assistant_coaches')
        }),
        ('Terrain', {
            'fields': ('default_venue',)
        }),
        ('Statistiques', {
            'fields': (
                'trophies_won', 'matches_played', 'matches_won', 'matches_drawn',
                'matches_lost', 'goals_for', 'goals_against'
            ),
            'classes': ('collapse',)
        }),
        ('Métadonnées', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    filter_horizontal = ('assistant_coaches',)
    inlines = [PlayerInline, TeamStaffInline]
    readonly_fields = ('id', 'created_at')

    def get_changeform_initial_data(self, request):
        return {'is_active': True}

    def coach_name(self, obj):
        return obj.coach.get_full_name() if obj.coach else 'Aucun'
    coach_name.short_description = 'Entraîneur'

    def players_count(self, obj):
        return obj.players.filter(is_active=True).count()
    players_count.short_description = 'Joueurs actifs'


# ─────────────────────────────────────────────
# Player
# ─────────────────────────────────────────────

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'team', 'jersey_number', 'position', 'birth_date', 'status', 'nationality', 'is_active')
    list_filter = ('status', 'is_active', 'position', 'team__club', 'team')
    search_fields = ('first_name', 'last_name', 'team__name', 'nationality')
    ordering = ('team', 'jersey_number')

    fieldsets = (
        ('Identité', {
            'fields': ('first_name', 'last_name', 'birth_date', 'birth_place', 'nationality', 'photo')
        }),
        ('Coordonnées', {
            'fields': ('address', 'city')
        }),
        ('Responsables légaux', {
            'fields': (
                'father_name', 'father_phone', 'father_email',
                'mother_name', 'mother_phone', 'mother_email',
            )
        }),
        ('Informations médicales', {
            'fields': ('blood_type', 'allergies', 'medical_authorization', 'treating_doctor', 'height', 'weight'),
            'classes': ('collapse',)
        }),
        ('Autorisations', {
            'fields': ('parental_authorization', 'transport_authorization', 'image_authorization', 'digital_signature'),
            'classes': ('collapse',)
        }),
        ('Données sportives', {
            'fields': ('team', 'category', 'jersey_number', 'position', 'is_captain', 'is_main_player',
                       'enrollment_date', 'status', 'is_active')
        }),
        ('Statistiques', {
            'fields': ('goals_scored', 'assists', 'yellow_cards', 'red_cards', 'minutes_played'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at',)

    def get_changeform_initial_data(self, request):
        return {'is_active': True, 'status': 'actif'}

    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = 'Nom complet'


# ─────────────────────────────────────────────
# TeamTournamentRegistration & TeamStaff
# ─────────────────────────────────────────────

@admin.register(TeamTournamentRegistration)
class TeamTournamentRegistrationAdmin(admin.ModelAdmin):
    list_display = ('team', 'tournament', 'group', 'registration_date', 'status')
    list_filter = ('status', 'tournament', 'registration_date')
    search_fields = ('team__name', 'tournament__name')
    ordering = ('-registration_date',)
    date_hierarchy = 'registration_date'

    fieldsets = (
        ('Inscription', {
            'fields': ('team', 'tournament', 'group')
        }),
        ('Statut', {
            'fields': ('status', 'seed_number')
        }),
        ('Notes', {
            'fields': ('special_requirements',),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('registration_date',)


@admin.register(TeamStaff)
class TeamStaffAdmin(admin.ModelAdmin):
    list_display = ('user_name', 'team', 'role', 'is_active')
    list_filter = ('role', 'is_active', 'team__club')
    search_fields = ('user__first_name', 'user__last_name', 'team__name')
    ordering = ('team', 'role')

    fieldsets = (
        ('Affectation', {
            'fields': ('user', 'team', 'role', 'is_active')
        }),
        ('Qualifications', {
            'fields': ('license_level', 'experience_years', 'specialization'),
            'classes': ('collapse',)
        }),
        ('Période', {
            'fields': ('start_date', 'end_date'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at',)

    def user_name(self, obj):
        return obj.user.get_full_name()
    user_name.short_description = 'Nom'


# ─────────────────────────────────────────────
# Season Stats Admin
# ─────────────────────────────────────────────

@admin.register(SeasonTeamStats)
class SeasonTeamStatsAdmin(admin.ModelAdmin):
    list_display = ('season', 'team', 'matches_played', 'matches_won', 'matches_drawn',
                    'matches_lost', 'goals_for', 'goals_against', 'trophies_won')
    list_filter = ('team', 'season')
    search_fields = ('team__name', 'season__name')
    readonly_fields = ('updated_at',)


@admin.register(SeasonPlayerStats)
class SeasonPlayerStatsAdmin(admin.ModelAdmin):
    list_display = ('player', 'season', 'matches_played', 'goals_scored',
                    'assists', 'yellow_cards', 'red_cards', 'average_rating')
    list_filter = ('season', 'player__team')
    search_fields = ('player__first_name', 'player__last_name', 'season__name')
    readonly_fields = ('updated_at',)


@admin.register(SeasonTournamentResult)
class SeasonTournamentResultAdmin(admin.ModelAdmin):
    list_display = ('team', 'tournament', 'season', 'final_position',
                    'points', 'is_champion', 'trophy_name')
    list_filter = ('is_champion', 'season', 'team')
    search_fields = ('team__name', 'tournament__name', 'season__name')
    readonly_fields = ('updated_at',)

