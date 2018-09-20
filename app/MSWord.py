from docx import Document
import io
import base64
import re

def toTOML(doc_string):
    full_text = "\n\n"
    with io.BytesIO(base64.decodebytes(bytes(doc_string, 'utf-8'))) as doc_file, io.StringIO() as ftext:
        ftext.write("\n\n")
        doc = Document(doc_file)
        for para in doc.paragraphs:
            txt = para.text
            sltxt = txt.strip().lower()
            if sltxt == ("works cited") or sltxt == ("referenes"):
                break
            if txt != "":
                ftext.write(txt + " PZPZPZ" + "\n\n")
                #full_text = full_text + txt + " PZPZPZ" + "\n\n"
        full_text = ftext.getvalue()
    return re.sub(r"\s+", ' ', full_text).strip()
