#!/usr/bin/env python3
"""Generate the complete, professionally formatted AI-VAPT Research Report DOCX."""

import os
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


def build_docx():
    doc = Document()

    # Margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

        # Header
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run("M.Tech Cyber Security Thesis Research Report | AI-VAPT Framework")
        hrun.font.size = Pt(8.5)
        hrun.font.color.rgb = RGBColor(128, 128, 128)

        # Footer
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        frun = fp.add_run("Page Reference Document | Antigravity Autonomous Audit")
        frun.font.size = Pt(8.5)
        frun.font.color.rgb = RGBColor(128, 128, 128)

    NAVY = RGBColor(31, 78, 121)
    DARK_GRAY = RGBColor(51, 51, 51)
    LIGHT_GRAY = RGBColor(110, 110, 110)

    def add_title(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(30)
        p.paragraph_format.space_after = Pt(12)
        run = p.add_run(text)
        run.font.size = Pt(22)
        run.font.bold = True
        run.font.color.rgb = NAVY
        return p

    def add_meta(text, italic=False, bold=False):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.font.size = Pt(11)
        run.font.italic = italic
        run.font.bold = bold
        run.font.color.rgb = DARK_GRAY
        return p

    def add_h1(text):
        p = doc.add_heading(level=1)
        p.paragraph_format.space_before = Pt(20)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.size = Pt(15)
        run.font.bold = True
        run.font.color.rgb = NAVY
        return p

    def add_h2(text):
        p = doc.add_heading(level=2)
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.size = Pt(12.5)
        run.font.bold = True
        run.font.color.rgb = DARK_GRAY
        return p

    def add_h3(text):
        p = doc.add_heading(level=3)
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.size = Pt(11)
        run.font.bold = True
        run.font.color.rgb = DARK_GRAY
        return p

    def add_body(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.15
        run = p.add_run(text)
        run.font.size = Pt(10.5)
        run.font.color.rgb = DARK_GRAY
        return p

    def add_callout(text, label="NOTE"):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.4)
        p.paragraph_format.right_indent = Inches(0.4)
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(8)
        r1 = p.add_run(f"[{label}] ")
        r1.font.bold = True
        r1.font.size = Pt(9.5)
        r1.font.color.rgb = NAVY
        r2 = p.add_run(text)
        r2.font.italic = True
        r2.font.size = Pt(9.5)
        r2.font.color.rgb = DARK_GRAY
        return p

    def add_fig(img_path, caption):
        full_path = (
            os.path.join("docs/research/final_report", img_path)
            if not os.path.exists(img_path)
            else img_path
        )
        if os.path.exists(full_path):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run()
            run.add_picture(full_path, width=Inches(5.8))

            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_after = Pt(12)
            r = cap.add_run(caption)
            r.font.size = Pt(9)
            r.font.italic = True
            r.font.color.rgb = LIGHT_GRAY

    def add_table(headers, rows):
        if not headers or not rows:
            return
        num_cols = len(headers)
        t = doc.add_table(rows=len(rows) + 1, cols=num_cols)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = True

        hdr_cells = t.rows[0].cells
        for i, title in enumerate(headers):
            hdr_cells[i].text = title
            p = hdr_cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(255, 255, 255)
            tcPr = hdr_cells[i]._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "1F4E79")
            tcPr.append(shd)

        for r_idx, row in enumerate(rows):
            row_cells = t.rows[r_idx + 1].cells
            # Normalize row length to num_cols
            norm_row = list(row) + [""] * (num_cols - len(row))
            norm_row = norm_row[:num_cols]
            for c_idx, val in enumerate(norm_row):
                row_cells[c_idx].text = str(val)
                p = row_cells[c_idx].paragraphs[0]
                for r in p.runs:
                    r.font.size = Pt(8.5)
                    r.font.color.rgb = DARK_GRAY
                if r_idx % 2 == 1:
                    tcPr = row_cells[c_idx]._tc.get_or_add_tcPr()
                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:val"), "clear")
                    shd.set(qn("w:color"), "auto")
                    shd.set(qn("w:fill"), "F2F4F7")
                    tcPr.append(shd)

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # Read the markdown source
    md_path = "docs/research/final_report/AI_VAPT_Comprehensive_Research_Report.md"
    with open(md_path, encoding="utf-8") as f:
        md_text = f.read()

    lines = md_text.splitlines()
    in_table = False
    table_headers = []
    table_rows = []

    print(f"Parsing {len(lines)} lines from {md_path}...")

    # Process markdown lines
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        idx += 1

        if not line:
            if in_table:
                add_table(table_headers, table_rows)
                in_table = False
                table_headers = []
                table_rows = []
            continue

        # Front matter title
        if line.startswith("# ") and "AI-Assisted" in line:
            add_title(line[2:])
            add_meta("A Comprehensive M.Tech Thesis Research & Engineering Report", italic=True)
            add_meta("Author: Vinit Solanki (M.Tech Cyber Security)", bold=True)
            add_meta("Repository Branch: development | Commit: a4af8fd")
            add_meta("Mentor Review Target: 27 October 2026")
            doc.add_page_break()
            continue

        # Heading 1
        if line.startswith("## "):
            if in_table:
                add_table(table_headers, table_rows)
                in_table = False
            add_h1(line[3:])
            continue

        # Heading 2
        if line.startswith("### "):
            if in_table:
                add_table(table_headers, table_rows)
                in_table = False
            add_h2(line[4:])
            continue

        # Heading 3
        if line.startswith("#### "):
            if in_table:
                add_table(table_headers, table_rows)
                in_table = False
            add_h3(line[5:])
            continue

        # Image embed
        img_match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
        if img_match:
            if in_table:
                add_table(table_headers, table_rows)
                in_table = False
            caption = img_match.group(1)
            img_rel = img_match.group(2)
            add_fig(img_rel, caption)
            continue

        # Blockquote / Callout
        if line.startswith("> "):
            callout_text = line[2:]
            add_callout(callout_text)
            continue

        # Table row
        if line.startswith("|") and line.endswith("|"):
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if all(set(p).issubset({"-", ":", " "}) for p in parts):
                continue  # separator row
            if not in_table:
                in_table = True
                table_headers = parts
                table_rows = []
            else:
                table_rows.append(parts)
            continue

        # Plain body paragraph or bullet
        if in_table:
            add_table(table_headers, table_rows)
            in_table = False

        if line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(line[2:])
            run.font.size = Pt(10)
            run.font.color.rgb = DARK_GRAY
        elif re.match(r"^\d+\.\s", line):
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(re.sub(r"^\d+\.\s", "", line))
            run.font.size = Pt(10)
            run.font.color.rgb = DARK_GRAY
        else:
            add_body(line)

    if in_table:
        add_table(table_headers, table_rows)

    out_docx = "docs/research/final_report/AI_VAPT_Comprehensive_Research_Report.docx"
    doc.save(out_docx)
    size_kb = os.path.getsize(out_docx) / 1024
    print(f"Generated DOCX report successfully: {out_docx} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    build_docx()
