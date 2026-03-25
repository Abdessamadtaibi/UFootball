from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'training-sessions', views.TrainingSessionViewSet, basename='training-session')
router.register(r'events', views.EventViewSet, basename='event')
router.register(r'convocations', views.ConvocationViewSet, basename='convocation')

app_name = 'planning'

urlpatterns = [
    path('', include(router.urls)),
]
