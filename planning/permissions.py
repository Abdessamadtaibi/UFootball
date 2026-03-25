from rest_framework.permissions import BasePermission


class IsStaffOrCoachForPlanningObject(BasePermission):
    """
    Permission for create / update / delete on TrainingSession and Event.
    - Staff  → club.owner == request.user
    - Coach  → team.coach == request.user
    - Parent → always denied (read-only)
    """

    def _is_staff_owner(self, user, team):
        return user.user_type == 'staff' and team.club.owner == user

    def _is_team_coach(self, user, team):
        return user.user_type == 'coach' and team.coach == user

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.user_type not in ('staff', 'coach'):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.user_type not in ('staff', 'coach'):
            return False

        team = _get_team(obj)
        if team is None:
            return False

        return self._is_staff_owner(user, team) or self._is_team_coach(user, team)


class IsParentForConvocationRespond(BasePermission):
    """
    Only parents can call the `respond` action on a Convocation,
    and only for convocations belonging to their own child.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.user_type == 'parent')

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        player = getattr(obj, 'player', None)
        if player is None:
            return False
        return user.email in (
            getattr(player, 'father_email', None),
            getattr(player, 'mother_email', None),
        )


# ── Internal helper ──────────────────────────────────────────

def _get_team(obj):
    """Resolve the Team from a TrainingSession, Event, or Convocation instance."""
    if hasattr(obj, 'team'):
        return obj.team
    if hasattr(obj, 'event') and obj.event:
        return obj.event.team
    return None
