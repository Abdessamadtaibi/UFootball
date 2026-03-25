from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from . import views
from planning import views as planning_views

# Root router
router = DefaultRouter()
router.register(r'clubs', views.ClubViewSet, basename='club')
router.register(r'public/teams', views.PublicTeamViewSet, basename='public-teams')

# Nested: clubs/<club_pk>/teams/
clubs_router = routers.NestedDefaultRouter(router, r'clubs', lookup='club')
clubs_router.register(r'teams', views.TeamViewSet, basename='team')
clubs_router.register(r'categories', views.CategoryViewSet, basename='category')

# Nested: clubs/<club_pk>/teams/<team_pk>/...
teams_router = routers.NestedDefaultRouter(clubs_router, r'teams', lookup='team')
teams_router.register(r'players', views.PlayerViewSet, basename='player')
teams_router.register(r'seasons', views.SeasonViewSet, basename='season')
teams_router.register(r'coaches', views.CoachViewSet, basename='coach')
# Planning endpoints nested under teams
teams_router.register(r'training-sessions', planning_views.TrainingSessionViewSet, basename='training-session')
teams_router.register(r'events', planning_views.EventViewSet, basename='event')

# Nested: clubs/<club_pk>/teams/<team_pk>/events/<event_pk>/convocations/
events_router = routers.NestedDefaultRouter(teams_router, r'events', lookup='event')
events_router.register(r'convocations', planning_views.ConvocationViewSet, basename='convocation')

app_name = 'teams'

urlpatterns = [
    path('', include(router.urls)),
    path('', include(clubs_router.urls)),
    path('', include(teams_router.urls)),
    path('', include(events_router.urls)),

    # Convenience endpoints
    path('my-clubs/', views.MyClubView.as_view(), name='my-clubs'),
    path('my-teams/', views.MyTeamView.as_view(), name='my-teams'),
    path('my-players/', views.MyPlayersView.as_view(), name='my-players'),
]