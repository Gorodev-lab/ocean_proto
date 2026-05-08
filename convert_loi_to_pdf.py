#!/usr/bin/env python3
"""Convert the LOI markdown to a professional 2-page PDF."""

import markdown
from weasyprint import HTML

MD_FILE = "Gorosave_LOI_oorg2026.md"
PDF_FILE = "Gorosave_LOI_oorg2026.pdf"

CSS = """
@page {
    size: letter;
    margin: 0.6in 0.7in;
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.35;
    color: #1a1a1a;
}

h1 {
    font-size: 13pt;
    color: #0b3d91;
    margin-bottom: 4px;
    line-height: 1.2;
    border-bottom: 2px solid #0b3d91;
    padding-bottom: 4px;
}

h2 {
    font-size: 11pt;
    color: #0b3d91;
    margin-top: 10px;
    margin-bottom: 4px;
}

h3 {
    font-size: 10pt;
    color: #333;
    margin-top: 8px;
    margin-bottom: 2px;
}

p {
    margin: 3px 0;
    text-align: justify;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 6px 0;
    font-size: 8.5pt;
}

th {
    background-color: #0b3d91;
    color: white;
    padding: 4px 6px;
    text-align: left;
    font-weight: 600;
}

td {
    padding: 3px 6px;
    border-bottom: 1px solid #ddd;
}

tr:nth-child(even) {
    background-color: #f8f9fa;
}

strong {
    color: #0b3d91;
}

ul, ol {
    margin: 3px 0;
    padding-left: 18px;
}

li {
    margin-bottom: 2px;
}
"""

with open(MD_FILE, "r") as f:
    md_text = f.read()

html_body = markdown.markdown(
    md_text,
    extensions=["tables", "smarty"],
)

full_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>{CSS}</style>
</head><body>{html_body}</body></html>"""

HTML(string=full_html).write_pdf(PDF_FILE)
print(f"✅ PDF generado: {PDF_FILE}")
