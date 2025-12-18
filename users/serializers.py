from rest_framework import serializers
from django.contrib.auth import get_user_model
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.conf import settings as djoser_settings
from .models import UserProfile

User = get_user_model()

print("DEBUG: users/serializers.py module loaded")


class UserCreateSerializer(BaseUserCreateSerializer):
    phone_number = serializers.CharField(max_length=15, required=False, allow_blank=True)
    user_type = serializers.ChoiceField(choices=User.USER_TYPES, required=False)

    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = BaseUserCreateSerializer.Meta.fields + ('phone_number', 'user_type')

    def create(self, validated_data):
        print("DEBUG: UserCreateSerializer.create called with:", validated_data)
        
        # Extract custom fields
        phone_number = validated_data.pop('phone_number', '')
        # Default new signups to 'parent' when not explicitly provided
        user_type = validated_data.pop('user_type', 'parent')
        
        print(f"DEBUG: Extracted phone_number: {phone_number}, user_type: {user_type}")
        
        # Call the parent create method
        try:
            user = super().create(validated_data)
            print(f"DEBUG: User created by parent: {user}")
        except Exception as e:
            print(f"DEBUG: Error in parent create: {e}")
            raise
        
        # Set custom fields
        user.phone_number = phone_number
        user.user_type = user_type
        
        # Activation policy:
        # - Staff/Admin accounts require admin activation (inactive by default)
        # - Parent/Viewer accounts: follow Djoser activation email setting; otherwise active
        if user_type in ('staff', 'admin'):
            user.is_active = False
            user.is_verified = False
        else:
            # Parent and Viewer accounts
            if djoser_settings.SEND_ACTIVATION_EMAIL:
                user.is_active = False
            else:
                user.is_active = True
            user.is_verified = False

        user.save(update_fields=[
            'phone_number', 'user_type', 'is_active', 'is_verified'
        ])
        
        print(f"DEBUG: User updated with phone_number: {user.phone_number}, user_type: {user.user_type}")
        
        return user

    def perform_create(self, validated_data):
        print("DEBUG: perform_create called with:", validated_data)
        
        # Extract custom fields
        phone_number = validated_data.pop('phone_number', '')
        # Default new signups to 'parent' when not explicitly provided
        user_type = validated_data.pop('user_type', 'parent')
        
        print(f"DEBUG: Extracted phone_number: {phone_number}, user_type: {user_type}")
        
        # Create user with remaining validated_data
        user = User.objects.create_user(**validated_data)
        
        # Set custom fields
        user.phone_number = phone_number
        user.user_type = user_type
        
        # Activation policy (same as in create)
        if user_type in ('staff', 'admin'):
            user.is_active = False
            user.is_verified = False
        else:
            # Parent and Viewer accounts
            if djoser_settings.SEND_ACTIVATION_EMAIL:
                user.is_active = False
            else:
                user.is_active = True
            user.is_verified = False

        user.save(update_fields=[
            'phone_number', 'user_type', 'is_active', 'is_verified'
        ])
        
        print(f"DEBUG: User created with phone_number: {user.phone_number}, user_type: {user.user_type}")
        
        # Handle activation email
        if djoser_settings.SEND_ACTIVATION_EMAIL:
            user.is_active = False
            user.save(update_fields=["is_active"])
        
        return user

    def to_representation(self, instance):
        """
        Return complete user data including custom fields
        """
        return {
            'id': instance.id,
            'username': instance.username,
            'email': instance.email,
            'first_name': instance.first_name,
            'last_name': instance.last_name,
            'phone_number': instance.phone_number,
            'user_type': instance.user_type,
            'is_verified': instance.is_verified
        }


class UserSerializer(serializers.ModelSerializer):
    """
    User serializer for API responses
    """
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'first_name', 'last_name', 
            'full_name', 'phone_number', 'user_type', 'profile_picture',
            'notifications_match_updates', 'notifications_tournament_news', 
            'notifications_team_news', 'is_verified'
        )
        read_only_fields = ('id', 'date_joined', 'last_login', 'is_verified')


class UserProfileSerializer(serializers.ModelSerializer):
    """
    User profile serializer
    """
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class NotificationPreferencesSerializer(serializers.ModelSerializer):
    """
    Serializer for updating notification preferences
    """
    class Meta:
        model = User
        fields = (
            'notifications_match_updates', 
            'notifications_tournament_news', 
            'notifications_team_news'
        )


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password
    """
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    confirm_password = serializers.CharField(required=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError("New passwords don't match.")
        return attrs


class UserListSerializer(serializers.ModelSerializer):
    """
    Simplified user serializer for lists
    """
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'first_name', 'last_name', 
            'full_name', 'user_type', 'is_active', 'is_verified', 'date_joined'
        )