from docx import Document

def crear_docx(contenido, titulo) -> str:
    doc = Document()
    doc.add_heading(titulo, 0)

    indice = next((item['texto'] for item in contenido if item['tipo'] == 'indice'), None)
    if indice:
        doc.add_heading('Índice', level=1)
        for linea in indice.split('\n'):
            doc.add_paragraph(linea.strip())

    for item in contenido:
        if item['tipo'] == 'capitulo':
            doc.add_page_break()
            doc.add_heading(f"Capítulo {item['numero']}", level=1)
            for parrafo in item['texto'].split('\n\n'):
                doc.add_paragraph(parrafo.strip())

    filename = "ebook_generado.docx"
    doc.save(filename)
    return filename
