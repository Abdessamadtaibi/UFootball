"""
PDF export for season reports using ReportLab.
Generates a structured PDF with team stats, player stats, and tournament results.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


def generate_season_pdf(season):
    """
    Generate a PDF report for a season.
    Returns an in-memory BytesIO buffer containing the PDF.
    """
    from teams.models import SeasonTeamStats, SeasonPlayerStats, SeasonTournamentResult

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=22,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#16213e'),
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#0f3460'),
        spaceBefore=20,
        spaceAfter=10,
        borderWidth=1,
        borderColor=colors.HexColor('#0f3460'),
        borderPadding=4,
    )
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#333333'),
    )

    elements = []
    team = season.team

    # ──────────────────────────────────────────
    # HEADER
    # ──────────────────────────────────────────
    elements.append(Paragraph(f"Rapport de Saison", title_style))
    elements.append(Paragraph(f"{team.club.name if team else ''}", subtitle_style))
    elements.append(Paragraph(f"Équipe: {team.name if team else 'N/A'}", body_style))
    elements.append(Paragraph(f"Saison: {season.name}", body_style))
    elements.append(Paragraph(
        f"Du {season.start_date.strftime('%d/%m/%Y')} au {season.end_date.strftime('%d/%m/%Y')}",
        body_style
    ))
    status = "Active" if season.is_active else "Terminée"
    elements.append(Paragraph(f"Statut: {status}", body_style))
    elements.append(Spacer(1, 8 * mm))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0f3460')))
    elements.append(Spacer(1, 8 * mm))

    # ──────────────────────────────────────────
    # ROSTER (player snapshot)
    # ──────────────────────────────────────────
    from teams.models import SeasonPlayerRoster

    roster = SeasonPlayerRoster.objects.filter(season=season).order_by('jersey_number')

    elements.append(Paragraph("👥 Effectif de la Saison", section_style))

    if roster.exists():
        data = [
            ['#', 'Joueur', 'Pos', 'Né le', 'Capitaine', 'Titulaire', 'Statut'],
        ]
        for entry in roster:
            data.append([
                str(entry.jersey_number),
                entry.full_name,
                entry.position or '-',
                entry.birth_date.strftime('%d/%m/%Y'),
                '✓' if entry.is_captain else '',
                '✓' if entry.is_main_player else '',
                entry.status,
            ])

        col_widths = [1.2 * cm, 4 * cm, 1.2 * cm, 2.5 * cm, 2 * cm, 2 * cm, 2 * cm]
        table = Table(data, colWidths=col_widths)
        table.setStyle(_player_table_style())
        elements.append(table)
    else:
        elements.append(Paragraph("Aucun effectif enregistré pour cette saison.", body_style))

    elements.append(Spacer(1, 10 * mm))
    elements.append(Spacer(1, 8 * mm))

    # ──────────────────────────────────────────
    # TEAM STATS
    # ──────────────────────────────────────────
    try:
        team_stats = season.team_stats
    except SeasonTeamStats.DoesNotExist:
        team_stats = None

    elements.append(Paragraph("📊 Statistiques de l'Équipe", section_style))

    if team_stats:
        gd = team_stats.goals_for - team_stats.goals_against
        gd_str = f"+{gd}" if gd > 0 else str(gd)
        pts = (team_stats.matches_won * 3) + team_stats.matches_drawn

        data = [
            ['Statistique', 'Valeur'],
            ['Matchs joués', str(team_stats.matches_played)],
            ['Victoires', str(team_stats.matches_won)],
            ['Nuls', str(team_stats.matches_drawn)],
            ['Défaites', str(team_stats.matches_lost)],
            ['Buts marqués', str(team_stats.goals_for)],
            ['Buts encaissés', str(team_stats.goals_against)],
            ['Différence de buts', gd_str],
            ['Points', str(pts)],
            ['Clean sheets', str(team_stats.clean_sheets)],
            ['Cartons jaunes', str(team_stats.yellow_cards)],
            ['Cartons rouges', str(team_stats.red_cards)],
            ['Trophées', str(team_stats.trophies_won)],
        ]
        if team_stats.best_finish:
            data.append(['Meilleur résultat', team_stats.best_finish])

        table = Table(data, colWidths=[10 * cm, 6 * cm])
        table.setStyle(_stats_table_style())
        elements.append(table)
    else:
        elements.append(Paragraph("Aucune statistique disponible.", body_style))

    elements.append(Spacer(1, 10 * mm))

    # ──────────────────────────────────────────
    # PLAYER STATS
    # ──────────────────────────────────────────
    player_stats = SeasonPlayerStats.objects.filter(
        season=season
    ).select_related('player').order_by('-goals_scored', '-assists')

    elements.append(Paragraph("⚽ Statistiques des Joueurs", section_style))

    if player_stats.exists():
        data = [
            ['#', 'Joueur', 'Pos', 'MJ', 'Tit', 'Min', 'Buts', 'PD', 'CJ', 'CR', 'Note'],
        ]
        for ps in player_stats:
            data.append([
                str(ps.player.jersey_number),
                ps.player.full_name,
                ps.player.position or '-',
                str(ps.matches_played),
                str(ps.matches_started),
                str(ps.minutes_played),
                str(ps.goals_scored),
                str(ps.assists),
                str(ps.yellow_cards),
                str(ps.red_cards),
                str(ps.average_rating) if ps.average_rating else '-',
            ])

        col_widths = [1 * cm, 4 * cm, 1.2 * cm, 1.2 * cm, 1.2 * cm, 1.4 * cm,
                      1.2 * cm, 1.2 * cm, 1.2 * cm, 1.2 * cm, 1.4 * cm]
        table = Table(data, colWidths=col_widths)
        table.setStyle(_player_table_style())
        elements.append(table)
    else:
        elements.append(Paragraph("Aucune statistique de joueur disponible.", body_style))

    elements.append(Spacer(1, 10 * mm))

    # ──────────────────────────────────────────
    # TOURNAMENT RESULTS
    # ──────────────────────────────────────────
    tournament_results = SeasonTournamentResult.objects.filter(
        season=season
    ).select_related('tournament').order_by('final_position')

    elements.append(Paragraph("🏆 Résultats des Tournois", section_style))

    if tournament_results.exists():
        for result in tournament_results:
            elements.append(Spacer(1, 4 * mm))
            trophy = f" — 🏆 {result.trophy_name}" if result.trophy_name else ""
            champion = " ⭐ CHAMPION" if result.is_champion else ""
            elements.append(Paragraph(
                f"<b>{result.tournament.name}</b>{trophy}{champion}",
                subtitle_style
            ))

            gd = result.goals_for - result.goals_against
            gd_str = f"+{gd}" if gd > 0 else str(gd)

            data = [
                ['Statistique', 'Valeur'],
                ['Position finale', f"#{result.final_position}" if result.final_position else 'N/A'],
                ['Groupe', result.group_name or 'N/A'],
                ['Position groupe', f"#{result.group_position}" if result.group_position else 'N/A'],
                ['Points', str(result.points)],
                ['Matchs (J/V/N/D)', f"{result.matches_played} / {result.matches_won} / {result.matches_drawn} / {result.matches_lost}"],
                ['Buts (Pour/Contre/Diff)', f"{result.goals_for} / {result.goals_against} / {gd_str}"],
            ]

            table = Table(data, colWidths=[8 * cm, 8 * cm])
            table.setStyle(_stats_table_style())
            elements.append(table)
    else:
        elements.append(Paragraph("Aucun résultat de tournoi disponible.", body_style))

    # ──────────────────────────────────────────
    # FOOTER
    # ──────────────────────────────────────────
    elements.append(Spacer(1, 15 * mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cccccc')))
    elements.append(Spacer(1, 4 * mm))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#999999'),
        alignment=TA_CENTER,
    )
    elements.append(Paragraph(
        f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — UFootball",
        footer_style
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _stats_table_style():
    """Standard table style for stats tables."""
    return TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f3460')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        # Body rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0f3460')),
    ])


def _player_table_style():
    """Table style for player stats table."""
    return TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        # Body rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Jersey #
        ('ALIGN', (2, 1), (-1, -1), 'CENTER'),  # All numeric cols
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#16213e')),
    ])
