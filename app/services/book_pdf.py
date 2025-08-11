from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

def build_book_pdf(path, titre, intro, sections):
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    margin = 2*cm
    y = height - margin

    def write_line(text, size=12, leading=16):
        nonlocal y
        if y < margin + leading:
            c.showPage(); y = height - margin
        c.setFont("Helvetica", size)
        c.drawString(margin, y, text)
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