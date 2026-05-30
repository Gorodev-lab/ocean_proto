#!/usr/bin/env python3
"""Convert CV markdown to professional PDF (max 5 pages)."""

import markdown
from weasyprint import HTML

MD_FILE = "cv gorosave.md"
PDF_FILE = "Gorosave_CV_oorg2026.pdf"

CSS = """
@page {
    size: letter;
    margin: 0.7in 0.8in;
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.4;
    color: #1a1a1a;
}

h1 {
    font-size: 16pt;
    color: #0b3d91;
    margin-bottom: 2px;
    border-bottom: 2.5px solid #0b3d91;
    padding-bottom: 6px;
}

h2 { display: none; }  /* hide the "---" h1 */

h3 {
    font-size: 12pt;
    color: #0b3d91;
    margin-top: 14px;
    margin-bottom: 4px;
    border-bottom: 1px solid #ccc;
    padding-bottom: 3px;
}

h4 {
    font-size: 10.5pt;
    color: #333;
    margin-top: 10px;
    margin-bottom: 2px;
}

p {
    margin: 4px 0;
    text-align: justify;
}

ul {
    margin: 4px 0;
    padding-left: 20px;
}

li {
    margin-bottom: 4px;
}

strong {
    color: #0b3d91;
}

em {
    color: #555;
}
"""

with open(MD_FILE, "r") as f:
    md_text = f.read()

# Remove the leading "# ---" line which creates an ugly header
md_text = md_text.replace("# ---\n", "")

html_body = markdown.markdown(md_text, extensions=["tables", "smarty"])
full_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>{CSS}</style>
</head><body>{html_body}</body></html>"""

doc = HTML(string=full_html).render()
doc.write_pdf(PDF_FILE)
print(f"✅ CV PDF generado: {PDF_FILE} ({len(doc.pages)} página(s))")
