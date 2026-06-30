"""PDF report generator for completed AgentX sessions.

Uses reportlab to produce a structured PDF with session metadata,
per-round scores, bug manifests, test results, and an overall summary.
"""

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)


def _build_styles():
    """Create custom paragraph styles on top of the default stylesheet."""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=6,
        spaceBefore=12,
        textColor=colors.HexColor("#1a1a2e"),
    ))
    styles.add(ParagraphStyle(
        "SmallBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
    ))
    return styles


def _score_color(total: int | float) -> colors.Color:
    """Return a green/yellow/red colour based on score (0-100)."""
    if total >= 75:
        return colors.HexColor("#27ae60")
    if total >= 50:
        return colors.HexColor("#f39c12")
    return colors.HexColor("#e74c3c")


def _make_session_info_table(state: dict, styles) -> Any:
    """Build a summary table of session metadata."""
    session_id = state.get("session_id", "N/A")
    language = state.get("language", "N/A")
    topic = state.get("topic", "N/A")
    difficulty = state.get("difficulty", "N/A")
    round_num = state.get("round_num", 0)
    max_rounds = state.get("max_rounds", 0)
    created_at = state.get("created_at", "N/A")

    data = [
        ["Session ID", str(session_id)],
        ["Language", language],
        ["Topic", topic],
        ["Difficulty", difficulty],
        ["Rounds Completed", f"{round_num} / {max_rounds}"],
        ["Created", str(created_at)],
    ]

    table = Table(data, colWidths=[2 * inch, 4 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#333333")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
    ]))
    return table


def _make_round_table(rounds: list[dict], styles) -> Any:
    """Build a per-round scores table."""
    header = ["Round", "Bugs Fixed", "Code Quality", "Speed Bonus", "Total"]
    rows = [header]

    for r in rounds:
        score = r.get("score")
        if not score:
            rows.append([str(r.get("round_num", "?")), "-", "-", "-", "-"])
            continue
        rows.append([
            str(r.get("round_num", "?")),
            f"{score.get('bugs_fixed', 0)} / {score.get('bugs_total', 0)}",
            f"{score.get('code_quality', 0):.0%}",
            f"{score.get('speed_bonus', 0):.1f}",
            str(score.get("total", 0)),
        ])

    table = Table(rows, colWidths=[0.8 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch, 1 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]))
    return table


def _make_bug_manifest_table(bug_manifest: list[dict], styles) -> Any:
    """Build a table listing injected bugs for a round."""
    if not bug_manifest:
        return Paragraph("<i>No bugs injected in this round.</i>", styles["SmallBody"])

    header = ["Line", "Type", "Description"]
    rows = [header]
    for bug in bug_manifest:
        rows.append([
            str(bug.get("line", "?")),
            bug.get("type", "unknown"),
            bug.get("description", ""),
        ])

    table = Table(rows, colWidths=[0.6 * inch, 1.2 * inch, 4.2 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _make_exec_result_block(label: str, exec_result: dict | None, styles) -> list:
    """Build a small section showing execution results for a code version."""
    elements = []
    elements.append(Paragraph(f"<b>{label}</b>", styles["SmallBody"]))
    if exec_result is None:
        elements.append(Paragraph("  Not executed.", styles["SmallBody"]))
    else:
        exit_code = exec_result.get("exit_code", "?")
        duration = exec_result.get("duration_ms", "?")
        stdout = exec_result.get("stdout", "")
        stderr = exec_result.get("stderr", "")
        status = "PASS" if exit_code == 0 else "FAIL"
        elements.append(
            Paragraph(
                f"  Status: <b>{status}</b> | Exit: {exit_code} | Duration: {duration}ms",
                styles["SmallBody"],
            )
        )
        if stderr:
            # Truncate long stderr
            short_stderr = stderr[:500] + ("..." if len(stderr) > 500 else "")
            elements.append(
                Paragraph(f"  Stderr: <font color='#e74c3c'>{short_stderr}</font>", styles["SmallBody"])
            )
    elements.append(Spacer(1, 4))
    return elements


def generate_session_report(state: dict) -> bytes:
    """Generate a PDF report for a completed session.

    Args:
        state: The full session state dict (must include `rounds` list).

    Returns:
        PDF bytes ready to be written to a file or returned as a response.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    styles = _build_styles()
    elements: list = []

    # ── Title ──
    elements.append(Paragraph("AgentX Session Report", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    elements.append(Spacer(1, 12))

    # ── Session Info ──
    elements.append(Paragraph("Session Overview", styles["SectionTitle"]))
    elements.append(_make_session_info_table(state, styles))
    elements.append(Spacer(1, 16))

    # ── Per-Round Breakdown ──
    rounds = state.get("rounds", [])
    if rounds:
        elements.append(Paragraph("Round Scores", styles["SectionTitle"]))
        elements.append(_make_round_table(rounds, styles))
        elements.append(Spacer(1, 16))

        # Per-round bug manifests and exec results
        for rnd in rounds:
            rnd_num = rnd.get("round_num", "?")
            elements.append(
                Paragraph(f"Round {rnd_num} — Details", styles["SectionTitle"])
            )

            # Bug manifest
            bug_manifest = rnd.get("bug_manifest", [])
            elements.append(Paragraph("<b>Bug Manifest</b>", styles["SmallBody"]))
            elements.append(_make_bug_manifest_table(bug_manifest, styles))
            elements.append(Spacer(1, 8))

            # Execution results
            elements.extend(_make_exec_result_block(
                "Original Code Execution", rnd.get("original_exec"), styles
            ))
            elements.extend(_make_exec_result_block(
                "Buggy Code Execution", rnd.get("buggy_exec"), styles
            ))
            elements.extend(_make_exec_result_block(
                "Student Fix Execution", rnd.get("fix_exec"), styles
            ))

            elements.append(HRFlowable(width="80%", thickness=0.5, color=colors.HexColor("#dddddd")))
            elements.append(Spacer(1, 8))
    else:
        elements.append(Paragraph(
            "<i>No rounds completed in this session.</i>", styles["BodyText"]
        ))

    # ── Overall Summary ──
    elements.append(Paragraph("Overall Summary", styles["SectionTitle"]))
    scored_rounds = [r for r in rounds if r.get("score")]
    if scored_rounds:
        totals = [r["score"]["total"] for r in scored_rounds]
        avg_total = sum(totals) / len(totals)
        total_bugs_fixed = sum(r["score"]["bugs_fixed"] for r in scored_rounds)
        total_bugs = sum(r["score"]["bugs_total"] for r in scored_rounds)

        summary_data = [
            ["Metric", "Value"],
            ["Rounds Scored", str(len(scored_rounds))],
            ["Average Score", f"{avg_total:.1f} / 100"],
            ["Total Bugs Fixed", f"{total_bugs_fixed} / {total_bugs}"],
            ["Overall Grade", _grade(avg_total)],
        ]
        summary_table = Table(summary_data, colWidths=[2.5 * inch, 2.5 * inch])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ]))
        elements.append(summary_table)
    else:
        elements.append(Paragraph(
            "<i>No scored rounds to summarize.</i>", styles["BodyText"]
        ))

    elements.append(Spacer(1, 24))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    elements.append(Paragraph(
        f"Generated by AgentX — {state.get('session_id', 'unknown')}",
        styles["SmallBody"],
    ))

    doc.build(elements)
    return buf.getvalue()


def _grade(avg: float) -> str:
    """Convert a 0-100 average to a letter grade."""
    if avg >= 90:
        return "A"
    if avg >= 80:
        return "B"
    if avg >= 70:
        return "C"
    if avg >= 60:
        return "D"
    return "F"
