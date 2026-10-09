import base64
import io
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

def notes_pdf(text=True):
    out=io.BytesIO();c=canvas.Canvas(out);c.setAuthor('private-test-author')
    if text:c.drawString(30,750,'Figure 1: measured XRD curve. Angle in degrees; intensity in counts.')
    else:c.line(30,100,400,400)
    c.showPage();c.save();return out.getvalue()

class NotesPDFTests(unittest.TestCase):
    def test_text_and_scan_keep_pdf_without_png_conversion(self):
        for has_text in (True,False):
            raw=notes_pdf(has_text);result=s.isolated_parse('notes-pdf',raw)
            self.assertEqual(result['pages'],1);self.assertNotIn('figures',result)
            self.assertEqual(bool(result['text']),has_text)
            if not has_text:self.assertIn('warning',result)
        with self.assertRaises(ValueError):s.isolated_parse('pdf',notes_pdf(False))
    def test_encryption_page_limit_and_malformed_rejected(self):
        for pages,password in ((21,None),(1,'test-password')):
            writer=PdfWriter()
            for _ in range(pages):writer.add_blank_page(width=100,height=100)
            if password:writer.encrypt(password)
            out=io.BytesIO();writer.write(out)
            with self.assertRaises(ValueError):s.isolated_parse('notes-pdf',out.getvalue())
        with self.assertRaises(ValueError):s.isolated_parse('notes-pdf',b'%PDF-bad')
    def test_original_binary_never_enters_prompt(self):
        from test_charts import figure_only
        raw=notes_pdf();data=figure_only()
        data['notesPDF']={'data':'data:application/pdf;base64,'+base64.b64encode(raw).decode(),'pages':1}
        prompt=s.make_prompt(data)
        self.assertNotIn('data:application/pdf',prompt);self.assertNotIn('private-test-author',prompt)
        self.assertIn('数据图说明',prompt)

if __name__=='__main__':unittest.main()
