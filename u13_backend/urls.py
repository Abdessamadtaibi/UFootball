"""
URL configuration for u13_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from users.views import activate_user_template_view, ResetPasswordView, CustomTokenCreateView

urlpatterns = [
    # Landing Page
    path('', TemplateView.as_view(template_name='home.html'), name='home'),

    # Admin interface
    path('admin/', admin.site.urls),
    
    # Custom login endpoint (must come before djoser.urls.authtoken)
    path('api/auth/token/login/', CustomTokenCreateView.as_view(), name='custom-token-login'),

    # Authentication endpoints (Djoser)
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.authtoken')),
    
    # App endpoints
    path('api/users/', include('users.urls')),
    path('api/clubs/', include('teams.urls')),
    path('api/teams/', include('teams.urls')),
    path('api/tournaments/', include('tournaments.urls')),
    path('api/matches/', include('matches.urls')),
    path('activate/<uid>/<token>/', activate_user_template_view, name='activate'),
    path('reset-password/<uid>/<token>/', ResetPasswordView.as_view(), name="reset-password"),
]

# Serve media files (always enabled for media to allow image uploads)
# In production, consider serving media files via Nginx or a CDN
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Serve static files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
