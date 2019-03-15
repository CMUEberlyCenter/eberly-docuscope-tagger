"""Utility function for decoding docx files."""
import io
import re
from docx import Document

def toTOML(doc_string):
    """Converts a docx string to TOML text.

    Arguments:
    - doc_string: (Bytes) a docx file.

    Returns:
    - (String) a TOML representation of the text in the docx file.
    """
    full_text = "\n\n"
    with io.BytesIO(doc_string) as doc_file,\
         io.StringIO() as ftext:
        ftext.write("\n\n")
        doc = Document(doc_file)
        for para in doc.paragraphs:
            txt = para.text
            sltxt = txt.strip().lower()
            if sltxt in ("works cited", "references"):
                break
            if txt != "":
                ftext.write(txt + " PZPZPZ" + "\n\n")
        full_text = ftext.getvalue()
    return re.sub(r"\s+", ' ', full_text).strip()
