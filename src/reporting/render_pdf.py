"""Render `reports/final_report.md` to a polished PDF for visual inspection.

Pure-Python toolchain (markdown -> HTML -> PDF via xhtml2pdf) so this needs no
system binary (no pandoc, no wkhtmltopdf, no native GTK/cairo for weasyprint) --
only two packages already installed for this purpose. This is presentation
only: it reads the already-written report and figures and lays them out. It
computes nothing and evaluates no data.

The report's own "Figures" table names each PNG; this renderer embeds them
inline as a two-up grid (figures are wide, and a 5-8 page budget does not fit
one figure per page here) immediately after that table, so the polished PDF
actually shows what the markdown only describes in words.
"""
from pathlib import Path
import base64
import re

import markdown

ROOT = Path(__file__).resolve().parents[2]
REPORT_MD = ROOT / "reports" / "final_report.md"
FIGURES_DIR = ROOT / "reports" / "figures"
OUT_PDF = ROOT / "reports" / "final_report.pdf"

FIGURE_FILES = (
    "01_cumulative_return.png", "02_sharpe_vs_cost.png", "03_rolling_beta.png",
    "04_factor_exposures.png", "05_candidate_grid.png", "06_drawdown.png",
)

CSS = """
@page { size: Letter; margin: 1.6cm 1.7cm 1.9cm 1.7cm;
  @frame footer { -pdf-frame-content: footerContent; bottom: 0.8cm; height: 1cm;
    left: 1.7cm; right: 1.7cm; } }
body { font-family: Helvetica, sans-serif; font-size: 9.3pt; line-height: 1.32;
  color: #1a1a1a; }
h1 { font-size: 16.5pt; margin: 0 0 4pt 0; color: #111; }
h2 { font-size: 12pt; margin: 14pt 0 5pt 0; color: #111;
  border-bottom: 0.75pt solid #999; padding-bottom: 2pt; }
h3 { font-size: 10.3pt; margin: 9pt 0 3pt 0; color: #222; }
p { margin: 4pt 0; text-align: justify; }
strong { color: #000; }
blockquote { margin: 6pt 10pt; padding: 5pt 9pt; background: #f2f2f2;
  border-left: 2.5pt solid #666; font-style: italic; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 8pt 0;
  font-size: 8.3pt; }
th, td { border: 0.5pt solid #999; padding: 2.6pt 5pt; text-align: left; }
th { background: #e4e4e4; font-weight: bold; }
code { font-family: Courier, monospace; font-size: 8.3pt; background: #eee;
  padding: 0 2pt; }
ul, ol { margin: 3pt 0 6pt 14pt; padding: 0; }
li { margin: 1.5pt 0; }
hr { border: none; border-top: 0.5pt solid #ccc; margin: 8pt 0; }
.subtitle { font-size: 9.5pt; color: #444; margin: 0 0 2pt 0; }
.meta { font-size: 8pt; color: #666; margin: 0 0 10pt 0; }
.figrow { width: 100%; margin: 4pt 0 8pt 0; }
.figcell { width: 50%; text-align: center; padding: 2pt; }
.figcell img { width: 260px; }
.figcap { font-size: 7.3pt; color: #555; }
#footerContent { font-size: 7.3pt; color: #888; text-align: center;
  border-top: 0.4pt solid #ccc; padding-top: 3pt; }
"""


def _b64_image(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _figure_grid_html() -> str:
    """A 2-up HTML table of the six figures, since xhtml2pdf has no flex/grid."""
    labels = {
        "01_cumulative_return.png": "Cumulative return: selection sample vs. sealed test",
        "02_sharpe_vs_cost.png": "Sharpe vs. assumed cost, both periods",
        "03_rolling_beta.png": "Rolling 252-day market beta vs. the +/-0.10 band",
        "04_factor_exposures.png": "Factor exposures, selection sample vs. sealed",
        "05_candidate_grid.png": "The 40-book candidate grid and the locked winner",
        "06_drawdown.png": "Drawdown from each period's own running peak",
    }
    cells = []
    for name in FIGURE_FILES:
        path = FIGURES_DIR / name
        img = _b64_image(path)
        cells.append(
            f'<td class="figcell"><img src="{img}"/>'
            f'<div class="figcap">{labels[name]}</div></td>')
    rows = "".join(f'<tr>{cells[i]}{cells[i+1]}</tr>' for i in range(0, len(cells), 2))
    return f'<table class="figrow">{rows}</table>'


def _inject_figures(html: str) -> str:
    """Insert the figure grid right after the report's own Figures table."""
    marker = "06_drawdown.png</code></td>\n<td>Drawdown from each period"
    idx = html.find("</table>", html.find(marker))
    if idx == -1:
        raise ValueError("could not locate the Figures table to insert images after")
    end = idx + len("</table>")
    return html[:end] + "\n" + _figure_grid_html() + html[end:]


def build_html() -> str:
    text = REPORT_MD.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    body = _inject_figures(body)
    # A light title block above the converted body, mirroring the .md's own H1/lede.
    match = re.match(r"<h1>(.*?)</h1>\s*<p><strong>(.*?)</strong></p>\s*<p>(.*?)</p>",
                      body, re.DOTALL)
    if match:
        title, question, meta = match.groups()
        header = (f"<h1>{title}</h1><p class='subtitle'>{question}</p>"
                  f"<p class='meta'>{meta}</p>")
        body = header + body[match.end():]
    return f"<html><head><style>{CSS}</style></head><body>{body}" \
           f"<div id='footerContent'>Cross-Sectional Alpha Research -- Project 1 -- " \
           f"generated from reports/final_report.md, not re-derived</div></body></html>"


def main() -> None:
    from xhtml2pdf import pisa

    html = build_html()
    with open(OUT_PDF, "wb") as f:
        result = pisa.CreatePDF(html, dest=f)
    if result.err:
        raise RuntimeError(f"{result.err} error(s) rendering PDF")
    print(f"Wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
