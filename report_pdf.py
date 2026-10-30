# -*- coding: utf-8 -*-
"""Отчёт для клиента в PDF (reportlab). Кириллический шрифт берётся из системы."""

import os
import sys
from datetime import datetime

from core import PART_NAMES, build_verdict, parts_table

FONT_CANDIDATES = [
    # (обычный, жирный)
    (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]

LEVEL_COLORS = {"red": ("#dc2626", "#fef2f2", "#b91c1c"),
                "orange": ("#ea580c", "#fff7ed", "#b45309"),
                "green": ("#16a34a", "#f0fdf4", "#15803d")}


def available():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return False
    return _fonts() is not None


def _fonts():
    for regular, bold in FONT_CANDIDATES:
        if os.path.isfile(regular):
            return regular, bold if os.path.isfile(bold) else regular
    return None


def _register():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    regular, bold = _fonts()
    pdfmetrics.registerFont(TTFont("RU", regular))
    pdfmetrics.registerFont(TTFont("RU-Bold", bold))


def build_pdf(path, logs, dev, device_lines, workshop="", repair=None, note=""):
    """repair — (datetime, заметка) последней отметки ремонта или None."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

    _register()
    st = {
        "h1": ParagraphStyle("h1", fontName="RU-Bold", fontSize=18, leading=22, spaceAfter=2),
        "small": ParagraphStyle("small", fontName="RU", fontSize=9, leading=12, textColor="#4b5563"),
        "cap": ParagraphStyle("cap", fontName="RU-Bold", fontSize=8, leading=11, textColor="#4b5563",
                              spaceBefore=4),
        "body": ParagraphStyle("body", fontName="RU", fontSize=10, leading=14),
        "h2": ParagraphStyle("h2", fontName="RU-Bold", fontSize=13, leading=17, spaceBefore=10, spaceAfter=4),
        "big": ParagraphStyle("big", fontName="RU-Bold", fontSize=16, leading=20),
    }

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title="Отчёт о диагностике iPhone", author=workshop or "iOS Panic Reader")
    width = A4[0] - 36 * mm
    story = []
    if workshop:
        story.append(Paragraph(esc(workshop), st["small"]))
    story.append(Paragraph("Отчёт о диагностике", st["h1"]))
    story.append(Paragraph(f"{datetime.now():%d.%m.%Y %H:%M}", st["small"]))
    story.append(Spacer(1, 8))

    rows = [[Paragraph(esc(k), st["cap"]), Paragraph(esc(v), st["body"])] for k, v in device_lines]
    if rows:
        t = Table(rows, colWidths=[45 * mm, width - 45 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#e3e7ec")),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)

    if repair:
        story.append(Paragraph("Проверка после ремонта", st["h2"]))
        when, rnote = repair
        story.append(Paragraph(f"Ремонт отмечен {when:%d.%m.%Y %H:%M}" + (f": {esc(rnote)}" if rnote else "") +
                               ". Ниже учитываются только сбои после ремонта.", st["body"]))

    problems = build_verdict(logs, dev)
    story.append(Paragraph("Результат", st["h2"]))
    if not problems:
        story.append(_box([Paragraph("Проблем не найдено", st["big"]),
                           Paragraph("В журналах телефона нет повторяющихся сбоев.", st["body"])],
                          "green", width))
    for i, p in enumerate(problems, 1):
        tag = "Важно" if p["level"] == "red" else "Не срочно"
        cell = [Paragraph(f"{i}. {esc(p['title'])} · {tag}", st["big"]),
                Paragraph("КАК ВЕДЁТ СЕБЯ", st["cap"]), Paragraph(esc(p["how"]), st["body"]),
                Paragraph("ПОЧЕМУ", st["cap"]), Paragraph(esc(p["why"]), st["body"]),
                Paragraph("ЧТО ДЕЛАТЬ", st["cap"])]
        cell += [Paragraph(f"{j}. {esc(f.rstrip('.'))}", st["body"]) for j, f in enumerate(p["fix"], 1)]
        cell.append(Paragraph("Основание: " + esc(p["note"]), st["small"]))
        story.append(_box(cell, p["level"], width))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Детали", st["h2"]))
    status = {"green": "в порядке", "orange": "подозрение", "red": "проблема"}
    trows = [[Paragraph(h, st["cap"]) for h in ("Деталь", "Данные", "Сбои в журналах", "Статус")]]
    styles = [("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e3e7ec")),
              ("VALIGN", (0, 0), (-1, -1), "TOP")]
    for i, (name, data, fails, lvl) in enumerate(parts_table(logs, dev), 1):
        trows.append([Paragraph(esc(name), st["body"]), Paragraph(esc(data), st["small"]),
                      Paragraph(esc(fails), st["small"]),
                      Paragraph(f'<font color="{LEVEL_COLORS[lvl][2]}">● {status[lvl]}</font>', st["body"])])
        if lvl != "green":
            styles.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(LEVEL_COLORS[lvl][1])))
    t = Table(trows, colWidths=[46 * mm, 38 * mm, width - 46 * mm - 38 * mm - 30 * mm, 30 * mm], repeatRows=1)
    t.setStyle(TableStyle(styles))
    story.append(t)

    if note:
        story.append(Paragraph("Заметка мастера", st["h2"]))
        story.append(Paragraph(esc(note).replace("\n", "<br/>"), st["body"]))

    story.append(Spacer(1, 14))
    story.append(Paragraph("Вывод основан на журналах сбоев iPhone и является ориентиром для диагностики.",
                           st["small"]))
    doc.build(story)


def _box(content, level, width):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    border, bg, _ = LEVEL_COLORS[level]
    t = Table([[content]], colWidths=[width])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor(border)),
                           ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    return t


if __name__ == "__main__":
    # Быстрая проверка: python report_pdf.py out.pdf <логи>
    from core import collect_files, parse_log
    logs = [parse_log(f) for f in collect_files(sys.argv[2:])]
    build_pdf(sys.argv[1], logs, None, [("Устройство", "тест")], "Мастерская [НАЗВАНИЕ]")
