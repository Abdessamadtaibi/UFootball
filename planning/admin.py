from django.contrib import admin
from .models import TrainingSession, Event, Convocation


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'team', 'category', 'coach', 'date', 'start_time', 'end_time', 'location', 'is_cancelled')
    list_filter = ('is_cancelled', 'team__club', 'date', 'category')
    search_fields = ('team__name', 'location', 'title', 'coach__last_name')
    ordering = ('-date', 'start_time')
    date_hierarchy = 'date'

    fieldsets = (
        ('Planification', {
            'fields': ('team', 'category', 'coach', 'season', 'date', 'start_time', 'end_time', 'location')
        }),
        ('Détails', {
            'fields': ('title', 'notes', 'recurrence')
        }),
        ('Annulation', {
            'fields': ('is_cancelled', 'cancellation_reason'),
            'classes': ('collapse',)
        }),
        ('Métadonnées', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at',)


class ConvocationInline(admin.TabularInline):
    model = Convocation
    extra = 0
    fields = ('player', 'status', 'notified', 'parent_response_at')
    readonly_fields = ('parent_response_at',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'event_type', 'team', 'date', 'start_time', 'location', 'status')
    list_filter = ('event_type', 'status', 'team__club', 'date')
    search_fields = ('title', 'opponent', 'location', 'team__name')
    ordering = ('-date', 'start_time')
    date_hierarchy = 'date'
    inlines = [ConvocationInline]

    fieldsets = (
        ('Informations générales', {
            'fields': ('event_type', 'title', 'team', 'season', 'status')
        }),
        ('Planification', {
            'fields': ('date', 'start_time', 'end_time', 'location', 'opponent')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at',)


@admin.register(Convocation)
class ConvocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'player', 'event', 'status', 'notified', 'parent_response_at')
    list_filter = ('status', 'notified')
    search_fields = ('player__first_name', 'player__last_name')
    ordering = ('-created_at',)

    fieldsets = (
        ('Convocation', {
            'fields': ('player', 'event', 'status')
        }),
        ('Notification', {
            'fields': ('notified', 'notified_at', 'parent_response_at', 'notes'),
        }),
    )
    readonly_fields = ('created_at', 'notified_at', 'parent_response_at')
