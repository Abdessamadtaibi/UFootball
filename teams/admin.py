from django.contrib import admin
from django.utils.html import format_html
from .models import Club, Team, Player, TeamTournamentRegistration, TeamStaff


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'short_name', 'founded_year', 'teams_count', 'is_active')
    list_filter = ('is_active', 'founded_year')
    search_fields = ('id', 'name', 'short_name', 'address')
    ordering = ('name',)
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('name', 'short_name', 'logo', 'is_active')
        }),
        ('Localisation', {
            'fields': ('address', 'phone', 'email', 'website')
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
        # Ensure new clubs are active by default in admin add form
        return {'is_active': True}
    
    def teams_count(self, obj):
        return obj.teams.count()
    teams_count.short_description = 'Nombre d\'équipes'


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0
    fields = ('jersey_number', 'first_name', 'last_name', 'position', 'birth_date', 'is_active')
    readonly_fields = ('created_at',)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Pre-check is_active for new inline player rows
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
    list_display = ('id', 'name', 'club', 'coach_name', 'category', 'players_count', 'is_active')
    list_filter = ('is_active', 'category', 'club')
    search_fields = ('id', 'name', 'club__name', 'coach__first_name', 'coach__last_name')
    ordering = ('club', 'name')
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('club', 'name', 'category', 'is_active')
        }),
        ('Encadrement', {
            'fields': ('coach', 'assistant_coaches')
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
        # Ensure new teams are active by default in admin add form
        return {'is_active': True}
    
    def coach_name(self, obj):
        return obj.coach.full_name if obj.coach else 'Aucun'
    coach_name.short_description = 'Entraîneur'
    
    def players_count(self, obj):
        return obj.players.filter(is_active=True).count()
    players_count.short_description = 'Joueurs actifs'


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'team', 'jersey_number', 'position', 'birth_date', 'age', 'is_active')
    list_filter = ('is_active', 'position', 'team__club', 'team')
    search_fields = ('first_name', 'last_name', 'team__name')
    ordering = ('team', 'jersey_number')
    
    fieldsets = (
        ('Informations personnelles', {
            'fields': ('first_name', 'last_name', 'birth_date', 'photo')
        }),
        ('Équipe', {
            'fields': ('team', 'jersey_number', 'position', 'is_active')
        }),
        ('Contacts d\'urgence', {
            'fields': ('parent_name', 'parent_phone', 'parent_email'),
            'classes': ('collapse',)
        }),
        ('Informations médicales', {
            'fields': ('height', 'weight'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('created_at',)

    def get_changeform_initial_data(self, request):
        # Ensure new players are active by default in admin add form
        return {'is_active': True}
    
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = 'Nom complet'
    
    def age(self, obj):
        if obj.birth_date:
            from datetime import date
            today = date.today()
            return today.year - obj.birth_date.year - ((today.month, today.day) < (obj.birth_date.month, obj.birth_date.day))
        return 'N/A'
    age.short_description = 'Âge'


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
    
    # Align with actual TeamStaff model fields
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
        return obj.user.full_name
    user_name.short_description = 'Nom'
