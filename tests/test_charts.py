import base64
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
from chart_import import svg_chart, pdf_charts
from PIL import Image
from pypdf import PdfWriter, PdfReader
from reportlab.pdfgen import canvas

SVG=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200"><metadata>private-test-metadata</metadata><rect width="400" height="200" fill="white"/><path d="M20 180 L80 100 L150 60 L300 140" fill="none" stroke="green"/></svg>'

def sample_pdf(pages=2):
    output=io.BytesIO();c=canvas.Canvas(output,pagesize=(400,240));c.setAuthor('private-test-author')
    for index in range(pages):
        c.line(20,20,380,20);c.line(20,20,20,220);c.drawString(30,210,f'Chart {index+1}')
        c.lines([(30,40,100,100),(100,100,200,180),(200,180,350,110)]);c.showPage()
    c.save();return output.getvalue()

def figure_only():
    return {'experiment':2,'rows':[],'process':'实际实验过程：研磨样品后装入样品台，按规定参数采集X射线衍射曲线。',
        'metadata':{'name':'虚构测试姓名','studentId':'DEMO-ONLY'},'chartNotes':'虚构测试姓名 图1：横轴为2θ，纵轴为counts。学号：DEMO-ONLY。峰形为本人描述，未提取精确坐标。',
        'figureDescriptions':['实验数据图1']}

class ChartTests(unittest.TestCase):
    def check_png(self,figure):
        raw=base64.b64decode(figure['data'].split(',')[1]);image=Image.open(io.BytesIO(raw))
        self.assertEqual(image.format,'PNG');self.assertEqual(image.mode,'RGB')
        self.assertLessEqual(image.width*image.height,2_000_000);self.assertFalse(image.getexif())
        self.assertNotIn(b'private-test',raw)
    def test_svg_and_standard_matplotlib_svg(self):
        self.check_png(s.isolated_parse('chart',SVG,{'kind':'svg','capacity':5})['figures'][0])
        from matplotlib.figure import Figure
        figure=Figure();figure.subplots().plot([0,1,2],[0,1,0]);target=io.BytesIO();figure.savefig(target,format='svg')
        result=s.isolated_parse('chart',target.getvalue(),{'kind':'svg','capacity':5})
        self.check_png(result['figures'][0])
    def test_svg_external_and_active_content_rejected_before_render(self):
        template='<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">%s</svg>'
        bad=['<script>alert(1)</script>','<image href="file:///private.png"/>','<use href="https://example.invalid/x.svg#x"/>','<foreignObject/>','<g onload="alert(1)"/>','<style>@import "https://example.invalid/style";</style>','<path style="fill:url(file:///private)"/>',r'<style>.a { fill:u\72l(file:///private); }</style>','<filter/>','<g xml:base="file:///private/"/>']
        with patch('resvg_py.svg_to_bytes') as renderer:
            for value in bad:
                with self.subTest(value=value),self.assertRaises(ValueError):svg_chart((template%value).encode())
            for value in [b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///private">]>'+SVG,b'<html/>',b'not xml',SVG*12000,b'<svg width="1e20" height="200"/>']:
                with self.assertRaises(ValueError):svg_chart(value)
            renderer.assert_not_called()
    def test_pdf_pages_normalized_atomically_and_capacity(self):
        result=s.isolated_parse('chart',sample_pdf(),{'kind':'pdf','capacity':5})
        self.assertEqual(result['pages'],2)
        for figure in result['figures']:self.check_png(figure)
        for raw,capacity in [(sample_pdf(),1),(sample_pdf(6),5)]:
            with self.assertRaisesRegex(ValueError,'最多还能添加'):s.isolated_parse('chart',raw,{'kind':'pdf','capacity':capacity})
    def test_pdf_encrypted_and_extreme_page_rejected(self):
        writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.encrypt('test-only-password');target=io.BytesIO();writer.write(target)
        with self.assertRaisesRegex(ValueError,'加密'):pdf_charts(target.getvalue(),5)
        writer=PdfWriter();writer.add_blank_page(width=100000,height=100000);target=io.BytesIO();writer.write(target)
        with self.assertRaisesRegex(ValueError,'尺寸'):pdf_charts(target.getvalue(),5)
    def test_figure_only_draft_prompt_and_no_fabricated_numbers(self):
        data=figure_only();draft=s.draft(data);prompt=s.make_prompt(data)
        self.assertIn('未提供数值表格',draft);self.assertIn('实验数据图1',draft);self.assertIn('不自动',prompt)
        self.assertIn('数据图说明',prompt);self.assertIn('不含图片像素',prompt);self.assertNotIn('DEMO-ONLY',prompt);self.assertNotIn('虚构测试姓名',prompt)
        self.assertIn('讨论与思考',draft);self.assertIn('参考文献',draft)
        with self.assertRaises(ValueError):s.analyze(2,[])
        with self.assertRaises(ValueError):s.make_prompt({**data,'rows':[{}]})
    def test_figure_only_pdf_embeds_all_charts(self):
        figures=pdf_charts(sample_pdf(),5)['figures'];figures=[{**f,'caption':'测试曲线'} for f in figures]
        reader=PdfReader(io.BytesIO(s.pdf_bytes('报告测试',s.draft(figure_only()),figures=figures)))
        self.assertIn('测试曲线',''.join(p.extract_text() for p in reader.pages))
        images=sum(len([v for v in page['/Resources'].get('/XObject',{}).values() if v.get_object().get('/Subtype')=='/Image']) for page in reader.pages)
        self.assertGreaterEqual(images,2)
    def test_chart_notes_length_and_type(self):
        for value in [None,{},'x'*18001]:
            with self.assertRaises(ValueError):s.make_prompt({**figure_only(),'chartNotes':value})

if __name__=='__main__':unittest.main()
