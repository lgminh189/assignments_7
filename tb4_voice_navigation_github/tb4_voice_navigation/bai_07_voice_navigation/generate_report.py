#!/usr/bin/env python3
"""Render the short Vietnamese Markdown report to a two-page PDF."""
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak


def main():
    root = Path(__file__).resolve().parent
    fonts = Path("/usr/share/fonts/truetype/dejavu")
    pdfmetrics.registerFont(TTFont("VN", str(fonts / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("VN-Bold", str(fonts / "DejaVuSans-Bold.ttf")))
    normal = ParagraphStyle("body", fontName="VN", fontSize=9, leading=13, spaceAfter=8)
    heading = ParagraphStyle("heading", parent=normal, fontName="VN-Bold", fontSize=11, leading=15, spaceBefore=8)
    title = ParagraphStyle("title", parent=heading, fontSize=15, leading=20, textColor=colors.HexColor("#16446b"))
    story = []
    for block in (root / "REPORT.md").read_text(encoding="utf-8").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block == "---PAGE---":
            story.append(PageBreak())
        elif block.startswith("!["):
            caption, path = re.fullmatch(r"!\[(.*?)\]\((.*?)\)", block).groups()
            story.extend([Image(str(root / path), width=155, height=250),
                          Paragraph(escape(caption), normal), Spacer(1, 4)])
        elif block.startswith("# "):
            story.append(Paragraph(escape(block[2:]), title))
        elif block.startswith("## "):
            story.append(Paragraph(escape(block[3:]), heading))
        else:
            story.append(Paragraph(escape(block), normal))

    def page_number(canvas, doc):
        canvas.setFont("VN", 8)
        canvas.drawRightString(A4[0]-40, 25, str(doc.page))

    doc = SimpleDocTemplate(str(root / "report.pdf"), pagesize=A4,
                            rightMargin=42, leftMargin=42, topMargin=35, bottomMargin=40,
                            title="Bài 7 — Phân vùng bản đồ và điều hướng bằng giọng nói")
    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    print(root / "report.pdf")


if __name__ == "__main__":
    main()
