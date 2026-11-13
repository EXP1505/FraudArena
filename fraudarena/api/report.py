"""Owner: M2. PDF of a verified rulebook (reportlab). Plain words first, evidence second."""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _t(s) -> str:
    """Helvetica has no rupee sign and a few other glyphs: map to safe text, then escape for Paragraph."""
    s = str(s if s is not None else "").replace("₹", "Rs ").replace("→", "->").replace("≥", ">=").replace("≤", "<=")
    return escape(s.encode("cp1252", "replace").decode("cp1252"))


def rulebook_pdf(doc: dict, patches: list[dict] | None = None, ledger_ok: bool | None = None) -> bytes:
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, alignment=0, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"))
    quote = ParagraphStyle("q", parent=body, leftIndent=8, borderPadding=4, textColor=colors.HexColor("#222222"))

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"FraudArena rulebook {doc['version']}", author="FraudArena")
    src = doc.get("data_source", {})
    el = [Paragraph(f"FraudArena rulebook {_t(doc['version'])}", h1),
          Paragraph(_t(f"Exported {doc.get('exported_at', 'n/a')}  |  Data source: {src.get('label', 'simulation')}  |  "
                       f"Parent: {doc.get('parent') or 'baseline'}"), small),
          HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#999999"), spaceBefore=4, spaceAfter=6)]
    ok_txt = {True: "Ledger chain verified at export time.", False: "WARNING: ledger chain did not verify.", None: ""}[ledger_ok]
    el.append(Paragraph(_t("Every rule here passed the automatic checks G1 to G6 and a second person's approval before going live "
                           "(the starting rulebook v1 is the baseline). Regulatory references are alignment notes, not a claim "
                           "of compliance. " + ok_txt), body))

    el.append(Paragraph("Rules in plain words", h2))
    for r in doc["rules"]:
        rows = [[Paragraph(f"<b>{_t(r['id'])}  {_t(r.get('title') or r['id'])}</b>", body),
                 Paragraph(f"<b>{_t(r.get('treatment') or r['action'])}</b>", body)]]
        rows.append([Paragraph("Fires when: " + _t(" AND ".join(f"{c['f']} {c['op']} {c['v']}" for c in r["when"])), body), ""])
        rows.append([Paragraph("Customer sees: " + _t('"' + (r.get("customer_message") or "") + '"'), quote), ""])
        why = r.get("rationale") or r.get("analyst_note") or ""
        if why:
            rows.append([Paragraph("Why: " + _t(why), body), ""])
        for x in r.get("reg_refs") or []:
            rows.append([Paragraph(_t(f"Basis ({x['strength']}): {x['instrument']}. {x['note']}"), small), ""])
        ev = r.get("evidence") or {}
        if "legit_flagged_pct_test" in ev:
            rows.append([Paragraph(_t(f"Evidence on RBIH test data: honest customers held {ev['legit_flagged_pct_test']:.2f}%, "
                                      f"mule accounts flagged {ev.get('mule_flagged_pct_test', 0):.2f}%."), small), ""])
        t = Table(rows, colWidths=[124 * mm, 46 * mm])
        t.setStyle(TableStyle([("SPAN", (0, i), (1, i)) for i in range(1, len(rows))] + [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDEDED")), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#BBBBBB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        el += [KeepTogether([t]), Spacer(1, 5)]

    appr = doc.get("approvals") or []
    if appr:
        el.append(Paragraph("How this version got here", h2))
        data = [["Proposal", "Rule", "Checks passed", "Written by", "Round started by", "Approved by", "Ledger #"]]
        for a in appr:
            data.append([_t(a.get("patch_id")), _t(a.get("rule_id")), _t(a.get("gates")), _t(a.get("maker")),
                         _t(a.get("starter") or "-"), _t(a.get("checker") or "-"), _t(a.get("ledger_seq") or "-")])
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDEDED")),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB"))]))
        el.append(t)

    el += [Paragraph("Integrity", h2),
           Paragraph(_t(f"SHA-256: {doc.get('sha256', 'unsealed')}"), small),
           Paragraph(_t(f"Signed with the ledger Ed25519 key. Public key: {doc.get('public_key', 'n/a')}"), small),
           Paragraph(_t("Verify the matching JSON export on the Rulebook page (Verify a file) or POST /api/rulebook/verify."), small)]
    pdf.build(el)
    return buf.getvalue()


def fidelity_pdf(doc: dict) -> bytes:
    """PDF of the fidelity certificate: score, per-feature table, rule check, limits, integrity."""
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"))
    rep = doc["report"]
    grid = [("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDEDED")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB"))]
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="FraudArena data fidelity", author="FraudArena")
    el = [Paragraph("Data fidelity: simulated world vs RBIH", h1),
          Paragraph(_t(f"Computed {doc.get('computed_at')}  |  Data source: {doc.get('data_source', {}).get('label')}"), small),
          Spacer(1, 6),
          Paragraph(_t(f"Realism score: {rep.get('score')} / 100 ({rep.get('band')}). Measured on {rep.get('measured_features')} of "
                       f"{rep.get('total_features')} features; the rest are not recorded by RBIH. Score = mean over features of "
                       f"100 x (1 - mean gap / {rep.get('tolerance_pp')} percentage points), computed at the same thresholds."), body),
          Paragraph("Per feature", h2)]
    rows = [["Feature", "Score", "Mean gap (pp)", "Band", "Simulated attacks vs real mules"]]
    for f in rep["features"]:
        ok = f.get("measurable")
        rows.append([_t(f["feature"]), _t(f.get("score")) if ok else "-", _t(f.get("mean_gap_pp")) if ok else "-",
                     _t(f.get("band")) if ok else "not measurable", Paragraph(_t(f.get("attack_note") or "-"), small)])
    t = Table(rows, repeatRows=1, colWidths=[38 * mm, 16 * mm, 24 * mm, 26 * mm, 66 * mm])
    t.setStyle(TableStyle(grid))
    el += [t, Paragraph("Rule friction: simulation vs RBIH", h2)]
    rows = [["Rule", "Condition", "RBIH %", "Sim %", "Note"]]
    for r in rep.get("rule_check", []):
        ok = r.get("checked")
        rows.append([Paragraph(_t(f"{r['rule_id']} {r.get('title') or ''}"), small), _t(r.get("condition", "-")),
                     _t(f"{r['rbih_friction_pct']:.2f}") if ok else "-", _t(f"{r['sim_friction_pct']:.2f}") if ok else "-",
                     Paragraph(_t(r.get("note", "")), small)])
    t = Table(rows, repeatRows=1, colWidths=[40 * mm, 38 * mm, 16 * mm, 16 * mm, 60 * mm])
    t.setStyle(TableStyle(grid))
    el += [t, Paragraph("Limits", h2)] + [Paragraph("- " + _t(x), small) for x in rep.get("limits", [])]
    el += [Paragraph("Integrity", h2), Paragraph(_t(f"SHA-256: {doc.get('sha256')}"), small),
           Paragraph(_t(f"Signed with the ledger Ed25519 key. Public key: {doc.get('public_key')}"), small)]
    pdf.build(el)
    return buf.getvalue()
