from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router for ViewSets
router = DefaultRouter()
router.register(r'matches', views.MatchViewSet, basename='match')
router.register(r'events', views.MatchEventViewSet, basename='matchevent')
router.register(r'lineups', views.MatchLineupViewSet, basename='matchlineup')
router.register(r'statistics', views.MatchStatisticsViewSet, basename='matchstatistics')
router.register(r'reports', views.MatchReportViewSet, basename='matchreport')

app_name = 'matches'

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Match management endpoints
    path('matches/<uuid:match_id>/start/', views.StartMatchView.as_view(), name='start-match'),
    path('matches/<uuid:match_id>/finish/', views.FinishMatchView.as_view(), name='finish-match'),
    path('matches/<uuid:match_id>/postpone/', views.PostponeMatchView.as_view(), name='postpone-match'),
    path('matches/<uuid:match_id>/cancel/', views.CancelMatchView.as_view(), name='cancel-match'),
    path('matches/<uuid:match_id>/reschedule/', views.RescheduleMatchView.as_view(), name='reschedule-match'),
    
    # Event management endpoints (nested under match)
    path('matches/<uuid:match_id>/events/', views.MatchEventsView.as_view(), name='match-events'),
    path('matches/<uuid:match_id>/events/<int:event_id>/', views.MatchEventDetailView.as_view(), name='match-event-detail'),
    
    # Lineup management endpoints
    path('matches/<uuid:match_id>/lineups/', views.MatchLineupsView.as_view(), name='match-lineups'),
    path('matches/<uuid:match_id>/lineups/<int:lineup_id>/', views.MatchLineupDetailView.as_view(), name='match-lineup-detail'),
    path('matches/<uuid:match_id>/set-lineup/', views.SetMatchLineupView.as_view(), name='set-lineup'),
    
    # Statistics endpoints
    path('matches/<uuid:match_id>/stats/', views.MatchStatsView.as_view(), name='match-stats'),
    path('matches/<uuid:match_id>/player-stats/', views.UpdatePlayerStatsView.as_view(), name='update-player-stats'),
    path('players/<int:player_id>/stats/', views.PlayerStatsView.as_view(), name='player-stats'),

    
    # Report management endpoints

    
    # Public endpoints

    path('public/live/', views.LiveMatchesView.as_view(), name='live-matches'),
    path('public/upcoming/', views.UpcomingMatchesView.as_view(), name='upcoming-matches'),
    path('public/recent/', views.RecentMatchesView.as_view(), name='recent-matches'),
    # Authenticated aliases (to match client services)
    path('upcoming/', views.UpcomingMatchesView.as_view(), name='upcoming-matches-auth'),
    path('recent/', views.RecentMatchesView.as_view(), name='recent-matches-auth'),
    path('live/', views.LiveMatchesView.as_view(), name='live-matches-auth'),
    
    # Calendar and schedule endpoints

    path('schedule/team/<int:team_id>/', views.TeamScheduleView.as_view(), name='team-schedule'),
    path('schedule/tournament/<uuid:tournament_id>/', views.TournamentScheduleView.as_view(), name='tournament-schedule'),
    
    # Search and filter endpoints
    path('search/', views.SearchMatchesView.as_view(), name='search-matches'),
    path('filter/', views.FilterMatchesView.as_view(), name='filter-matches'),
]