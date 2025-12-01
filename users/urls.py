from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for ViewSets
router = DefaultRouter()
router.register(r'profiles', views.UserProfileViewSet, basename='userprofile')

app_name = 'users'

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Custom user endpoints
    path('me/', views.CurrentUserView.as_view(), name='current-user'),
    path('me/profile/', views.CurrentUserProfileView.as_view(), name='current-user-profile'),
    path('update-preferences/', views.UpdateNotificationPreferencesView.as_view(), name='update-preferences'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('upload-avatar/', views.UploadAvatarView.as_view(), name='upload-avatar'),
    
    # Admin endpoints for user management
    path('list/', views.UserListView.as_view(), name='user-list'),
    path('<uuid:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('<uuid:pk>/activate/', views.ActivateUserView.as_view(), name='activate-user'),
    path('<uuid:pk>/deactivate/', views.DeactivateUserView.as_view(), name='deactivate-user'),
]