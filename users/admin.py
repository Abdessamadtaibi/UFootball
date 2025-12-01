from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import User, UserProfile
 



@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Configuration de l'administration pour le modèle User personnalisé
    """
    
    # Champs affichés dans la liste
    list_display = ('id', 'email', 'full_name', 'user_type', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('user_type', 'is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    ordering = ('email',)
    
    # Configuration des formulaires
    fieldsets = (
        (_('Identifiants'), {
            'fields': ('id',),
        }),
        (None, {'fields': ('email', 'password')}),
        (_('Informations personnelles'), {
            'fields': ('first_name', 'last_name', 'phone_number', 'profile_picture')
        }),
        (_('Type d\'utilisateur'), {
            'fields': ('user_type',)
        }),
        (_('Préférences'), {
            'fields': ('notifications_match_updates', 'notifications_tournament_news', 'notifications_team_news')
        }),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Dates importantes'), {
            'fields': ('last_login', 'date_joined')
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'user_type', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('id', 'date_joined', 'last_login')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('profile')

    

    # Supprimer toute inline liée aux jetons (aucune liste visible)
    def get_inline_instances(self, request, obj=None):
        return []

    # Actions superuser: activer/désactiver Admin/Organisateur
    actions = ['activate_admins', 'deactivate_admins']

    @admin.action(description=_('Activer les Admin/Organisateurs'))
    def activate_admins(self, request, queryset):
        qs = queryset.filter(user_type='admin')
        updated = qs.update(is_active=True)
        self.message_user(request, _('%d comptes Admin/Organisateur activés.') % updated)

    @admin.action(description=_('Désactiver les Admin/Organisateurs'))
    def deactivate_admins(self, request, queryset):
        qs = queryset.filter(user_type='admin')
        updated = qs.update(is_active=False)
        self.message_user(request, _('%d comptes Admin/Organisateur désactivés.') % updated)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop('activate_admins', None)
            actions.pop('deactivate_admins', None)
        return actions


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Configuration de l'administration pour les profils utilisateur
    """
    
    list_display = ('user', 'get_user_type', 'bio_preview', 'created_at')
    list_filter = ('user__user_type', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'bio')
    
    fieldsets = (
        (_('Utilisateur'), {
            'fields': ('user',)
        }),
        (_('Informations générales'), {
            'fields': ('bio', 'address', 'emergency_contact', 'emergency_phone')
        }),
        (_('Informations spécifiques - Parents'), {
            'fields': ('children_names',),
            'classes': ('collapse',),
        }),
        (_('Informations spécifiques - Staff'), {
            'fields': ('coaching_license', 'experience_years', 'specialization'),
            'classes': ('collapse',),
        }),
        (_('Informations spécifiques - Admin'), {
            'fields': ('organization', 'position'),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at')
    
    def get_user_type(self, obj):
        return obj.user.get_user_type_display()
    get_user_type.short_description = 'Type d\'utilisateur'
    
    def bio_preview(self, obj):
        if obj.bio:
            return obj.bio[:50] + '...' if len(obj.bio) > 50 else obj.bio
        return '-'
    bio_preview.short_description = 'Bio (aperçu)'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
