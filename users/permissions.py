from rest_framework.permissions import BasePermission


class IsAuthenticatedAnd(BasePermission):
    """
    Helper permission base that ensures the user is authenticated first.
    Subclasses should implement `_passes(user)`.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and self._passes(user))

    def has_object_permission(self, request, view, obj):
        user = request.user
        return bool(user and user.is_authenticated and self._passes(user))

    def _passes(self, user):
        return False


class IsAdminUserType(IsAuthenticatedAnd):
    def _passes(self, user):
        # Admin/Organisateur must be active and verified to manage
        return (
            getattr(user, 'is_admin_user', lambda: False)() and
            getattr(user, 'is_active', False) and
            getattr(user, 'is_verified', False)
        )


class IsAdminActiveUserType(IsAuthenticatedAnd):
    """
    Permission: Admin/Organisateur actif (sans exiger la vérification).
    Utile pour permettre la création d'un tournoi aux comptes admin actifs
    même si la vérification n'est pas encore complétée.
    """

    def _passes(self, user):
        return (
            getattr(user, 'is_admin_user', lambda: False)() and
            getattr(user, 'is_active', False)
        )


class IsStaffUserType(IsAuthenticatedAnd):
    def _passes(self, user):
        return getattr(user, 'is_staff_member', lambda: False)()


class IsParentUserType(IsAuthenticatedAnd):
    def _passes(self, user):
        return getattr(user, 'is_parent', lambda: False)()


class IsAdminOrStaffUserType(IsAuthenticatedAnd):
    def _passes(self, user):
        return (
            getattr(user, 'is_admin_user', lambda: False)() or
            getattr(user, 'is_staff_member', lambda: False)()
        )

class IsAdminOrStaffOrParentUserType(IsAuthenticatedAnd):
    def _passes(self, user):
        return (
            getattr(user, 'is_admin_user', lambda: False)() or
            getattr(user, 'is_staff_member', lambda: False)() or
            getattr(user, 'is_parent', lambda: False)()
        )

class IsStaffOrCoachUserType(IsAuthenticatedAnd):
    def _passes(self, user):
        return (
            getattr(user, 'is_staff_member', lambda: False)() or
            getattr(user, 'is_coach', lambda: False)()
        )

class IsCoachOrAdminForTeam(BasePermission):
    """
    Object-level permission for Team management:
    - Admins pass
    - Team coach or assistant coaches pass
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Admin always allowed
        if getattr(user, 'is_admin_user', lambda: False)():
            return True

        # Expecting obj to be a Team-like instance
        coach = getattr(obj, 'coach', None)
        assistants = getattr(obj, 'assistant_coaches', None)

        if coach and coach == user:
            return True

        try:
            if assistants and user in assistants.all():
                return True
        except Exception:
            pass

        return False


class IsMatchCoachOrAdmin(BasePermission):
    """
    Object-level permission for match-related objects:
    - Admins pass
    - Coaches/assistants of either team in the match pass
    Works with Match, MatchEvent, MatchLineup, MatchStatistics.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Admin always allowed
        if getattr(user, 'is_admin_user', lambda: False)():
            return True

        match = None
        # Resolve match from object
        if hasattr(obj, 'home_team') and hasattr(obj, 'away_team'):
            match = obj
        elif hasattr(obj, 'match'):
            match = getattr(obj, 'match')
        elif hasattr(obj, 'team') and hasattr(obj, 'match'):
            match = getattr(obj, 'match')

        if not match:
            return False

        home = getattr(match, 'home_team', None)
        away = getattr(match, 'away_team', None)

        def is_authorized_for_team(team):
            if not team:
                return False
            # Check if user is coach
            if getattr(team, 'coach', None) == user:
                return True
            # Check if user is club owner
            if hasattr(team, 'club') and getattr(team.club, 'owner', None) == user:
                return True
            # Check if user is assistant coach
            assistants = getattr(team, 'assistant_coaches', None)
            try:
                if assistants and user in assistants.all():
                    return True
            except Exception:
                pass
            
            # Check if user is in TeamStaff
            if hasattr(team, 'staff') and team.staff.filter(user=user, is_active=True).exists():
                return True
                
            return False

        return is_authorized_for_team(home) or is_authorized_for_team(away)


class IsSuperUser(BasePermission):
    """Permission: only Django superusers pass."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, 'is_superuser', False))


class IsOrganizerOrSuperUser(BasePermission):
    """
    Object-level permission for Tournament-like objects:
    - Superuser passes
    - Organizer (obj.organizer) passes
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        organizer = getattr(obj, 'organizer', None)
        try:
            return organizer and organizer == user
        except Exception:
            return False