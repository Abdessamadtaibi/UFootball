from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
# Register specific endpoints FIRST to avoid them being captured as IDs by TournamentViewSet
router.register(r'groups', views.TournamentGroupViewSet, basename='tournament-group')
router.register(r'phases', views.TournamentPhaseViewSet, basename='tournament-phase')

router.register(r'matches', views.MatchViewSet, basename='match')
# Register main tournament viewset LAST
router.register(r'', views.TournamentViewSet, basename='tournament')
 
urlpatterns = [
    
    # Tournament-specific endpoints (format: <uuid>/endpoint/)
    path('<uuid:tournament_id>/teams/', views.TournamentTeamsView.as_view(), name='tournament-teams'),
    path('<uuid:tournament_id>/standings/', views.TournamentStandingsView.as_view(), name='tournament-standings'),
    path('<uuid:tournament_id>/stats/', views.TournamentStatsView.as_view(), name='tournament-stats'),
    path('<uuid:tournament_id>/start/', views.StartTournamentView.as_view(), name='tournament-start'),
    path('<uuid:tournament_id>/finish/', views.FinishTournamentView.as_view(), name='tournament-finish'),
    path('<uuid:tournament_id>/cancel/', views.CancelTournamentView.as_view(), name='tournament-cancel'),
    
    # Router URLs (this handles list, create, retrieve, update, delete)
    path('', include(router.urls)),
]