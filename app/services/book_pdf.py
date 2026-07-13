from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.utils import simpleSplit


def build_book_pdf(path, titre, intro, sections):
    """Génère le PDF d'accueil léger.

    ``sections`` : liste de paires ``(titre_section, contenu)`` (le contenu peut
    contenir des retours à la ligne). Les lignes trop larges sont enveloppées
    (word-wrap) pour ne jamais déborder de la page.
    """
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    margin = 2*cm
    max_width = width - 2 * margin
    y = height - margin

    def write_line(text, size=12, leading=16):
        nonlocal y
        # Word-wrap : découpe la ligne à la largeur utile de la page.
        for chunk in (simpleSplit(str(text), "Helvetica", size, max_width) or [""]):
            if y < margin + leading:
                c.showPage(); y = height - margin
            c.setFont("Helvetica", size)
            c.drawString(margin, y, chunk)
            y -= leading

    write_line(titre, size=18, leading=24)
    write_line(" ")
    for line in (intro or "").splitlines():
        write_line(line, size=11, leading=15)
    write_line(" ")

    for title, content in sections or []:
        write_line(title, size=14, leading=20)
        for line in (content or "").splitlines():
            write_line("• " + line, size=11, leading=15)
        write_line(" ")

    c.save()