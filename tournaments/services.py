from itertools import combinations
from math import log2, ceil
from datetime import datetime, timedelta, time
from django.db import transaction

from .models import (
    Tournament, TournamentGroup, TournamentPhase,
    TeamGroup, Match
)


class TournamentEngine:
    """Core engine for automating tournament flow."""

    def __init__(self, tournament: Tournament):
        self.tournament = tournament

    # ──────────────────────────────────────────────
    # 1. GROUP STAGE GENERATION
    # ──────────────────────────────────────────────

    def generate_group_stage_matches(self):
        """
        Generate all round-robin matches for every group.
        Creates placeholder match slots with scheduled status.
        """
        tournament = self.tournament
        groups = tournament.groups.prefetch_related('team_groups__team').all()

        # NEW: For league type, if no group exists, auto-create one with all registered teams
        if not groups.exists() and tournament.tournament_type == 'league':
            from teams.models import TeamTournamentRegistration
            # Get all confirmed teams for this tournament
            registrations = TeamTournamentRegistration.objects.filter(
                tournament=tournament, status='confirmed'
            ).select_related('team')
            
            if registrations.exists():
                # Create the single "Ligue" group
                group = TournamentGroup.objects.create(
                    tournament=tournament,
                    name='Ligue',
                    order=1
                )
                # Add all teams to this group
                for idx, reg in enumerate(registrations, 1):
                    TeamGroup.objects.create(
                        team=reg.team,
                        group=group,
                        position=idx
                    )
                # Refresh groups queryset
                groups = tournament.groups.prefetch_related('team_groups__team').all()

        if not groups.exists():
            raise ValueError("Aucun groupe trouvé. Créez des groupes et ajoutez des équipes d'abord.")

        # Get or create group_stage phase
        group_phase, _ = TournamentPhase.objects.get_or_create(
            tournament=tournament,
            phase_type='group_stage',
            defaults={
                'name': 'Phase de groupes' if tournament.tournament_type != 'league' else 'Ligue',
                'order': 1,
                'start_date': tournament.start_date,
                'end_date': tournament.end_date,
            }
        )

        all_matches = []
        match_counter = 1
        base_date = (
            datetime.combine(tournament.start_date, time.min)
            if tournament.start_date else datetime.now()
        )

        venues = self._get_venues()

        for group in groups:
            teams = list(group.team_groups.select_related('team').all())
            team_objects = [tg.team for tg in teams]

            if len(team_objects) < 2:
                continue

            # Generate round-robin pairs
            pairs = list(combinations(team_objects, 2))
            
            # number_of_legs should be at least 1, but for league we often want 2 (aller-retour)
            num_legs = tournament.number_of_legs
            if tournament.tournament_type == 'league' and num_legs < 1:
                num_legs = 1 # Safety default

            for leg in range(1, num_legs + 1):
                for i, (team_a, team_b) in enumerate(pairs):
                    # For round-robin, we want a simple round number
                    # This is a simplified scheduling logic
                    round_number = (i // (max(1, len(team_objects) // 2))) + 1
                    
                    if leg == 1:
                        home, away = team_a, team_b
                    else:
                        home, away = team_b, team_a

                    # Spread matches across time slots
                    match_offset = timedelta(
                        days=(match_counter - 1) // 4,
                        hours=((match_counter - 1) % 4) * 2
                    )
                    match_date = base_date + match_offset

                    venue = venues[(match_counter - 1) % len(venues)] if venues else ''

                    match = Match(
                        tournament=tournament,
                        group=group,
                        phase=group_phase,
                        home_team=home,
                        away_team=away,
                        match_date=match_date,
                        venue=venue,
                        round_number=round_number + (leg - 1) * (len(pairs) // (max(1, len(team_objects) // 2)) + 1),
                        match_number=match_counter,
                        status='scheduled',
                    )
                    all_matches.append(match)
                    match_counter += 1

        Match.objects.bulk_create(all_matches)
        return all_matches

    # ──────────────────────────────────────────────
    # 2. KNOCKOUT BRACKET GENERATION
    # ──────────────────────────────────────────────

    def generate_knockout_bracket(self):
        """
        After group stage is complete, generate the knockout bracket
        with placeholder matches. Teams are filled based on group standings.
        """
        tournament = self.tournament

        if tournament.tournament_type == 'league':
            raise ValueError("Les tournois de type championnat n'ont pas de phase éliminatoire.")

        # Check group stage is complete
        if not self._is_group_stage_complete():
            raise ValueError(
                "La phase de groupes n'est pas terminée. "
                "Tous les matchs de groupe doivent être joués."
            )

        # Mark group phase as completed
        group_phase = TournamentPhase.objects.filter(
            tournament=tournament, phase_type='group_stage'
        ).first()
        if group_phase:
            group_phase.is_completed = True
            group_phase.is_active = False
            group_phase.save()

        # Determine qualified teams
        qualified_teams = self._get_qualified_teams()
        num_teams = len(qualified_teams)

        if num_teams < 2:
            raise ValueError("Pas assez d'équipes qualifiées pour la phase éliminatoire.")

        # Determine knockout phases needed
        knockout_phases = self._calculate_knockout_phases(num_teams)
        venues = self._get_venues()

        # Create phases and matches
        created_matches = {}  # {phase_type: [matches]}
        base_date = (
                        datetime.combine(tournament.end_date or tournament.start_date, time.min)
                    ) - timedelta(days=len(knockout_phases))

        phase_order = 10  # Start after group stage
        match_counter = Match.objects.filter(tournament=tournament).count() + 1

        for phase_idx, phase_info in enumerate(knockout_phases):
            phase_type = phase_info['type']
            phase_name = phase_info['name']
            num_matches = phase_info['num_matches']

            phase, _ = TournamentPhase.objects.get_or_create(
                tournament=tournament,
                phase_type=phase_type,
                defaults={
                    'name': phase_name,
                    'order': phase_order,
                    'start_date': base_date + timedelta(days=phase_idx),
                    'end_date': base_date + timedelta(days=phase_idx),
                }
            )
            phase_order += 1

            phase_matches = []
            for match_idx in range(num_matches):
                match_offset = timedelta(
                    days=phase_idx,
                    hours=match_idx * 2
                )
                match_date = base_date + match_offset
                venue = venues[match_idx % len(venues)] if venues else ''

                match = Match(
                    tournament=tournament,
                    phase=phase,
                    group=None,
                    home_team=None,
                    away_team=None,
                    match_date=match_date,
                    venue=venue,
                    match_number=match_counter,
                    round_number=1,
                    status='scheduled',
                    bracket_position=match_idx + 1,
                    bracket_round=phase_idx + 1,
                )
                phase_matches.append(match)
                match_counter += 1

            Match.objects.bulk_create(phase_matches)
            # Re-fetch to get IDs
            phase_matches = list(
                Match.objects.filter(tournament=tournament, phase=phase)
                .order_by('bracket_position')
            )
            created_matches[phase_type] = phase_matches

        # Link matches: winner of match N goes to next round
        self._link_bracket_matches(created_matches, knockout_phases)

        # Fill first round with qualified teams
        first_phase_type = knockout_phases[0]['type']
        first_round_matches = created_matches[first_phase_type]
        self._seed_first_round(first_round_matches, qualified_teams)

        # Generate 3rd place match if configured
        if tournament.third_place_match:
            third_match = self._create_third_place_match(
                tournament, base_date, len(knockout_phases), match_counter, venues
            )
            # If there are no semi-finals (e.g. only 2 qualified → direct final),
            # fill the 3rd place match immediately with the eliminated teams
            has_semis = any(p['type'] == 'semi_final' for p in knockout_phases)
            if not has_semis and third_match:
                eliminated = self._get_eliminated_teams(qualified_teams)
                if len(eliminated) >= 2:
                    third_match.home_team = eliminated[0]
                    third_match.away_team = eliminated[1]
                    third_match.save()

        tournament.bracket_generated = True
        tournament.save()

        return created_matches

    def _seed_first_round(self, matches, qualified_teams):
        """
        Seed qualified teams into the first knockout round.

        When teams_qualify_per_group == 1:
          - Only group winners qualify, so pair them directly:
            1st of Group A vs 1st of Group B, etc.

        When teams_qualify_per_group >= 2:
          - Classic cross-seeding: 1A vs 2B, 1B vs 2A, etc.
        """
        teams_per_group = self.tournament.teams_qualify_per_group

        if teams_per_group == 1:
            # Direct pairing: team 0 vs team 1, team 2 vs team 3, etc.
            seeded_pairs = []
            team_list = [t[0] for t in qualified_teams]  # extract Team objects
            for i in range(0, len(team_list) - 1, 2):
                seeded_pairs.append((team_list[i], team_list[i + 1]))
        else:
            # Cross-seeding: pair group winners with runners-up of other groups
            firsts = [t for t in qualified_teams if t[2] == 1]
            seconds = [t for t in qualified_teams if t[2] == 2]
            others = [t for t in qualified_teams if t[2] > 2]

            # Reverse seconds for cross-matching (1A vs 2B, 1B vs 2A)
            seconds_reversed = list(reversed(seconds))

            seeded_pairs = []
            for i in range(min(len(firsts), len(seconds_reversed))):
                seeded_pairs.append((firsts[i][0], seconds_reversed[i][0]))

            # Handle remaining teams (if teams_qualify_per_group > 2)
            remaining = others[:]
            for i in range(len(seeded_pairs), len(matches)):
                if len(remaining) >= 2:
                    t1 = remaining.pop(0)
                    t2 = remaining.pop(0)
                    seeded_pairs.append((t1[0], t2[0]))

        # Assign teams to matches
        for i, match in enumerate(matches):
            if i < len(seeded_pairs):
                match.home_team = seeded_pairs[i][0]
                match.away_team = seeded_pairs[i][1]
                match.home_team_placeholder = ''
                match.away_team_placeholder = ''
                match.save()

    def _link_bracket_matches(self, created_matches, knockout_phases):
        """Link matches so winners auto-advance to the next round."""
        for phase_idx in range(len(knockout_phases) - 1):
            current_type = knockout_phases[phase_idx]['type']
            next_type = knockout_phases[phase_idx + 1]['type']

            current_matches = created_matches[current_type]
            next_matches = created_matches[next_type]

            for i, next_match in enumerate(next_matches):
                # Match i in next round receives winners from matches 2i and 2i+1
                match_a_idx = i * 2
                match_b_idx = i * 2 + 1

                if match_a_idx < len(current_matches):
                    current_matches[match_a_idx].next_match = next_match
                    current_matches[match_a_idx].next_match_slot = 'home'
                    current_matches[match_a_idx].save()

                if match_b_idx < len(current_matches):
                    current_matches[match_b_idx].next_match = next_match
                    current_matches[match_b_idx].next_match_slot = 'away'
                    current_matches[match_b_idx].save()

    def _create_third_place_match(self, tournament, base_date, num_phases, match_counter, venues):
        """Create the 3rd place playoff match. Returns the created Match object."""
        phase, _ = TournamentPhase.objects.get_or_create(
            tournament=tournament,
            phase_type='third_place',
            defaults={
                'name': 'Match pour la 3ème place',
                'order': 99,
                'start_date': base_date + timedelta(days=num_phases),
                'end_date': base_date + timedelta(days=num_phases),
            }
        )

        venue = venues[0] if venues else ''
        match = Match.objects.create(
            tournament=tournament,
            phase=phase,
            group=None,
            home_team=None,
            away_team=None,
            match_date=base_date + timedelta(days=num_phases, hours=-2),
            venue=venue,
            match_number=match_counter,
            round_number=1,
            status='scheduled',
            bracket_position=1,
            bracket_round=num_phases,
            is_third_place_match=True,
        )
        return match

    # ──────────────────────────────────────────────
    # 3. WINNER PROPAGATION
    # ──────────────────────────────────────────────

    @staticmethod
    def propagate_winner(match):
        """
        After a knockout match is finished, push the winner
        to the linked next_match slot (home or away).
        Also handle semi-final losers → 3rd place match.
        """
        if match.status != 'finished':
            return
        if not match.phase:
            return

        winner = match.winner
        loser = match.loser
        if not winner:
            return  # Draw in knockout – shouldn't happen normally

        # Propagate winner to next match
        if match.next_match:
            next_match = match.next_match
            if match.next_match_slot == 'home':
                next_match.home_team = winner
            elif match.next_match_slot == 'away':
                next_match.away_team = winner
            next_match.save()

        # Handle semi-final losers → 3rd place match
        if match.phase.phase_type == 'semi_final' and loser:
            tournament = match.tournament
            if tournament.third_place_match:
                third_place_match = Match.objects.filter(
                    tournament=tournament,
                    is_third_place_match=True
                ).first()

                if third_place_match:
                    if third_place_match.home_team is None:
                        third_place_match.home_team = loser
                    elif third_place_match.away_team is None:
                        third_place_match.away_team = loser
                    third_place_match.save()

        # Check if this was the final → set tournament winner
        if match.phase.phase_type == 'final':
            tournament = match.tournament
            tournament.winner = winner
            tournament.runner_up = loser
            tournament.status = 'finished'
            tournament.save()
            TournamentEngine._update_season_stats(tournament)

        # Check if 3rd place match is finished
        if match.is_third_place_match:
            tournament = match.tournament
            tournament.third_place = winner
            tournament.save()

        # Check if phase is complete
        TournamentEngine._check_phase_completion(match)

    @staticmethod
    def _check_phase_completion(match):
        """Mark phase as completed if all its matches are finished."""
        phase = match.phase
        if not phase:
            return

        total = phase.matches.count()
        finished = phase.matches.filter(status='finished').count()

        if total > 0 and total == finished:
            phase.is_completed = True
            phase.is_active = False
            phase.save()

    # ──────────────────────────────────────────────
    # 4. LEAGUE WINNER DETERMINATION
    # ──────────────────────────────────────────────

    def determine_league_winner(self):
        """For league tournaments, determine winner from standings."""
        tournament = self.tournament
        if tournament.tournament_type != 'league':
            return

        group = tournament.groups.first()
        if not group:
            return

        # Check all matches are finished
        total = Match.objects.filter(tournament=tournament, group=group).count()
        finished = Match.objects.filter(
            tournament=tournament, group=group, status='finished'
        ).count()

        if total == 0 or total != finished:
            return

        standings = group.get_standings()
        if len(standings) >= 1:
            tournament.winner = standings[0]['team']
        if len(standings) >= 2:
            tournament.runner_up = standings[1]['team']
        if len(standings) >= 3:
            tournament.third_place = standings[2]['team']

        tournament.status = 'finished'
        tournament.save()
        
        TournamentEngine._update_season_stats(tournament)

        return standings

    # ──────────────────────────────────────────────
    # 5. SEASON STATS UPDATE
    # ──────────────────────────────────────────────
    
    @staticmethod
    def _update_season_stats(tournament):
        """Update season stats for the teams that reached final stages."""
        from teams.models import SeasonTournamentResult, SeasonTeamStats, Season
        from django.db.models import F
        
        # Get all teams that participated in this tournament
        # Determine the current active season for each team and update
        
        # 1. Update Winner
        if tournament.winner:
            # Check if there is an active season
            season = Season.objects.filter(team=tournament.winner, is_active=True).first()
            if season:
                # Update SeasonTournamentResult
                result, created = SeasonTournamentResult.objects.get_or_create(
                    season=season,
                    team=tournament.winner,
                    tournament=tournament,
                    defaults={'final_position': 1, 'is_champion': True, 'trophy_name': 'Vainqueur'}
                )
                if not created:
                    result.final_position = 1
                    result.is_champion = True
                    result.trophy_name = 'Vainqueur'
                    result.save()
                    
                # Update Team stats
                team_stats, _ = SeasonTeamStats.objects.get_or_create(season=season, team=tournament.winner)
                team_stats.trophies_won = F('trophies_won') + 1
                team_stats.best_finish = 'Vainqueur'
                team_stats.save()
                
                # Also update global Team model
                tournament.winner.trophies_won = F('trophies_won') + 1
                tournament.winner.save()
                
        # 2. Update Runner-up
        if tournament.runner_up:
            season = Season.objects.filter(team=tournament.runner_up, is_active=True).first()
            if season:
                result, created = SeasonTournamentResult.objects.get_or_create(
                    season=season,
                    team=tournament.runner_up,
                    tournament=tournament,
                    defaults={'final_position': 2, 'trophy_name': 'Finaliste'}
                )
                if not created:
                    result.final_position = 2
                    result.trophy_name = 'Finaliste'
                    result.save()
                    
                team_stats, _ = SeasonTeamStats.objects.get_or_create(season=season, team=tournament.runner_up)
                if team_stats.best_finish != 'Vainqueur':
                    team_stats.best_finish = 'Finaliste'
                    team_stats.save()
                    
        # 3. Update Third place
        if tournament.third_place:
            season = Season.objects.filter(team=tournament.third_place, is_active=True).first()
            if season:
                result, created = SeasonTournamentResult.objects.get_or_create(
                    season=season,
                    team=tournament.third_place,
                    tournament=tournament,
                    defaults={'final_position': 3, 'trophy_name': 'Troisième place'}
                )
                if not created:
                    result.final_position = 3
                    result.trophy_name = 'Troisième place'
                    result.save()
                    
                team_stats, _ = SeasonTeamStats.objects.get_or_create(season=season, team=tournament.third_place)
                if team_stats.best_finish not in ['Vainqueur', 'Finaliste']:
                    team_stats.best_finish = 'Demi-finaliste'
                    team_stats.save()
                    
        # 4. Update Semi-finalists (if knockout)
        if tournament.tournament_type == 'group_knockout':
            semi_finals = Match.objects.filter(
                tournament=tournament, 
                phase__phase_type='semi_final'
            )
            for sf_match in semi_finals:
                loser = sf_match.loser
                if loser and loser != tournament.third_place:
                    season = Season.objects.filter(team=loser, is_active=True).first()
                    if season:
                        result, created = SeasonTournamentResult.objects.get_or_create(
                            season=season,
                            team=loser,
                            tournament=tournament,
                            defaults={'final_position': 4, 'trophy_name': 'Demi-finaliste'}
                        )
                        if not created:
                            result.final_position = 4
                            result.trophy_name = 'Demi-finaliste'
                            result.save()
                            
                        team_stats, _ = SeasonTeamStats.objects.get_or_create(season=season, team=loser)
                        if team_stats.best_finish not in ['Vainqueur', 'Finaliste']:
                            team_stats.best_finish = 'Demi-finaliste'
                            team_stats.save()

    # ──────────────────────────────────────────────
    # 6. GROUP STAGE COMPLETION CHECK
    # ──────────────────────────────────────────────

    def check_group_stage_and_generate_knockout(self):
        """
        Check if group stage is complete. If so, auto-generate knockout.
        Called after every group match finishes.
        """
        if self.tournament.tournament_type != 'group_knockout':
            return False

        if self.tournament.bracket_generated:
            return False

        if not self._is_group_stage_complete():
            return False

        self.generate_knockout_bracket()
        return True

    # ──────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────

    def _is_group_stage_complete(self):
        """Check if all group stage matches are finished."""
        group_matches = Match.objects.filter(
            tournament=self.tournament,
            group__isnull=False
        )
        if not group_matches.exists():
            return False

        return not group_matches.exclude(status='finished').exists()

    def _get_qualified_teams(self):
        """
        Get qualified teams from group standings.
        Returns list of (team, group_order, position_in_group).
        """
        tournament = self.tournament
        qualified = []

        groups = tournament.groups.order_by('order').all()
        for group in groups:
            standings = group.get_standings()
            for standing in standings[:tournament.teams_qualify_per_group]:
                team = standing['team']
                position = standing['position']

                # Mark as qualified in TeamGroup
                try:
                    tg = TeamGroup.objects.get(team=team, group=group)
                    tg.is_qualified = True
                    tg.qualified_position = position
                    tg.save()
                except TeamGroup.DoesNotExist:
                    pass

                qualified.append((team, group.order, position))

        return qualified

    def _get_eliminated_teams(self, qualified_teams):
        """
        Get eliminated teams (non-qualified) from group standings.
        Used to fill the 3rd place match when there are no semi-finals.
        Returns a list of Team objects, ordered by their position across groups.
        """
        tournament = self.tournament
        qualified_team_ids = {t[0].id for t in qualified_teams}
        eliminated = []

        groups = tournament.groups.order_by('order').all()
        for group in groups:
            standings = group.get_standings()
            # Skip qualified teams, take the next best (position just after qualification cutoff)
            for standing in standings[tournament.teams_qualify_per_group:]:
                eliminated.append(standing['team'])

        return eliminated

    def _get_venues(self):
        """Parse venues from tournament."""
        if not self.tournament.venues:
            return [self.tournament.location] if self.tournament.location else ['']
        return [v.strip() for v in self.tournament.venues.strip().split('\n') if v.strip()]

    def _calculate_knockout_phases(self, num_teams):
        """Calculate which knockout phases are needed."""
        phases_map = {
            2: [{'type': 'final', 'name': 'Finale', 'num_matches': 1}],
            4: [
                {'type': 'semi_final', 'name': 'Demi-finales', 'num_matches': 2},
                {'type': 'final', 'name': 'Finale', 'num_matches': 1},
            ],
            8: [
                {'type': 'quarter_final', 'name': 'Quarts de finale', 'num_matches': 4},
                {'type': 'semi_final', 'name': 'Demi-finales', 'num_matches': 2},
                {'type': 'final', 'name': 'Finale', 'num_matches': 1},
            ],
            16: [
                {'type': 'round_16', 'name': 'Huitièmes de finale', 'num_matches': 8},
                {'type': 'quarter_final', 'name': 'Quarts de finale', 'num_matches': 4},
                {'type': 'semi_final', 'name': 'Demi-finales', 'num_matches': 2},
                {'type': 'final', 'name': 'Finale', 'num_matches': 1},
            ],
        }

        # Find the next power of 2
        target = 2 ** ceil(log2(num_teams)) if num_teams > 1 else 2

        if target in phases_map:
            return phases_map[target]

        # Dynamic generation for unusual numbers
        phases = []
        current = target
        round_num = 1
        while current > 1:
            num_matches = current // 2
            if current == 2:
                phase_type = 'final'
                name = 'Finale'
            elif current == 4:
                phase_type = 'semi_final'
                name = 'Demi-finales'
            elif current == 8:
                phase_type = 'quarter_final'
                name = 'Quarts de finale'
            elif current == 16:
                phase_type = 'round_16'
                name = 'Huitièmes de finale'
            else:
                phase_type = f'round_{current}'
                name = f'Tour de {current}'

            phases.append({
                'type': phase_type,
                'name': name,
                'num_matches': num_matches
            })
            current //= 2
            round_num += 1

        return phases