from django.shortcuts import render
from rest_framework import generics, viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import UserProfile
from django.views import View
import requests
from django.shortcuts import render, redirect
from .serializers import (
    UserSerializer, UserProfileSerializer, 
    NotificationPreferencesSerializer, ChangePasswordSerializer
)
from .permissions import IsAdminUserType, IsSuperUser

User = get_user_model()


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """
    Get and update current user information
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class CurrentUserProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and update current user profile
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile


class UserProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user profiles
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.is_admin_user() or self.request.user.is_staff:
            return UserProfile.objects.all()
        return UserProfile.objects.filter(user=self.request.user)


class UpdateNotificationPreferencesView(APIView):
    """
    Update user notification preferences
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request):
        serializer = NotificationPreferencesSerializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    Change user password
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            
            # Check old password
            if not user.check_password(serializer.validated_data['old_password']):
                return Response(
                    {'old_password': ['Wrong password.']}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Validate new password
            try:
                validate_password(serializer.validated_data['new_password'], user)
            except ValidationError as e:
                return Response(
                    {'new_password': e.messages}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Set new password
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            return Response({'message': 'Password changed successfully.'})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UploadAvatarView(APIView):
    """
    Upload user avatar
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        if 'avatar' not in request.FILES:
            return Response(
                {'error': 'No avatar file provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        user.profile_picture = request.FILES['avatar']
        user.save()
        
        serializer = UserSerializer(user)
        return Response(serializer.data)


# Admin views
class UserListView(generics.ListAPIView):
    """
    List all users (admin only)
    """
    serializer_class = UserSerializer
    permission_classes = [IsAdminUserType]
    queryset = User.objects.all()


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Get, update, or delete a specific user (admin only)
    """
    serializer_class = UserSerializer
    permission_classes = [IsAdminUserType]
    queryset = User.objects.all()
    lookup_field = 'id'


class ActivateUserView(APIView):
    """
    Activate a user account (superuser only)
    """
    permission_classes = [IsSuperUser]
    
    def post(self, request, pk):
        try:
            user = User.objects.get(id=pk)
            user.is_active = True
            user.is_verified = True
            user.save()
            return Response({'message': 'User activated successfully'})
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )


class DeactivateUserView(APIView):
    """
    Deactivate a user account (superuser only)
    """
    permission_classes = [IsSuperUser]
    
    def post(self, request, pk):
        try:
            user = User.objects.get(id=pk)
            user.is_active = False
            user.save()
            return Response({'message': 'User deactivated successfully'})
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )


def activate_user_template_view(request, uid, token):
    activation_url = f"http://127.0.0.1:8000/api/auth/users/activation/"
    data = {"uid": uid, "token": token}
    response = requests.post(activation_url, data=data)

    if response.status_code == 204:
        return render(request, "activation_success.html")
    else:
        return render(request, "activation_failed.html")


class ResetPasswordView(View):
    def get(self, request, uid, token):
        # Show the reset form
        return render(request, "reset_password.html", {"uid": uid, "token": token})

    def post(self, request, uid, token):
        new_password = request.POST.get("new_password")
        re_password = request.POST.get("re_password")

        if new_password != re_password:
            return render(request, "reset_password.html", {
                "uid": uid,
                "token": token,
                "error": "Passwords do not match"
            })

        # Call Djoser's reset_password_confirm endpoint
        response = requests.post(
            "http://127.0.0.1:8000/api/auth/users/reset_password_confirm/",
            json={"uid": uid, "token": token, "new_password": new_password},
        )

        if response.status_code == 204:  # success
            return render(request, "reset_success.html")
        else:
            return render(request, "reset_error.html")


