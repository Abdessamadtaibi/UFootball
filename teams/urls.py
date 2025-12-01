from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from . import views

# Create a router for ViewSets
router = DefaultRouter()
router.register(r'clubs', views.ClubViewSet, basename='club')
router.register(r'public/teams', views.PublicTeamViewSet, basename='public-teams')
clubs_router = routers.NestedDefaultRouter(router, r'clubs', lookup='club')

clubs_router.register(r'teams', views.TeamViewSet, basename='team')
teams_router = routers.NestedDefaultRouter(clubs_router, r'teams', lookup='team')

teams_router.register(r'players', views.PlayerViewSet, basename='player')
players_router = routers.NestedDefaultRouter(teams_router,r'players', lookup='player' )

app_name = 'teams'

urlpatterns = [
    path('', include(router.urls)),
    path('', include(clubs_router.urls)),
    path('', include(teams_router.urls)),
    
    # Additional endpoints
    path('my-clubs/', views.MyClubView.as_view(), name='my-clubs'),
    path('my-teams/', views.MyTeamView.as_view(), name='my-teams'),
    path('my-players/', views.MyPlayersView.as_view(), name='my-players'),
] 