import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
from math_layout import FORMULAS, segments, validate_tex
from pypdf import PdfReader

class MathTests(unittest.TestCase):
    def test_course_sources_and_both_pdf_forms(self):
        self.assertEqual(len(FORMULAS),60)
        self.assertEqual({f['experiment'] for f in FORMULAS},set(range(1,11)))
        for f in FORMULAS:
            self.assertIn(f['source'],'\n'.join(s.experiment(f['experiment'])['theory']))
            self.assertEqual(segments(f['source'])[0]['tex'],f['tex'])
        result=s.isolated_parse('math',json.dumps([f['tex'] for f in FORMULAS]).encode())
        self.assertEqual(len(result['formulas']),60)
        for image in result['formulas']:
            self.assertGreater(image['width'],0)
            self.assertLess(image['width'],A4_WIDTH)
    def test_delimiters_and_unmatched_text(self):
        self.assertEqual(segments(r'文字 \(x^2\) 与 \[\frac{1}{2}\]')[1],{'kind':'math','tex':'x^2','display':False})
        parts=segments('$$\n'+r'\int_0^1 x\,dx'+'\n$$')
        self.assertEqual(parts[0]['tex'],r'\int_0^1 x\,dx')
        for value in [r'价格 $12 和 $18',r'未闭合 \(x',r'转义 \\(x\\)',r'只有 $$']:
            self.assertEqual(segments(value,known=False),[{'kind':'text','text':value}])
    def test_dangerous_or_unbounded_commands_rejected(self):
        for tex in [r'\input{/etc/passwd}',r'\href{https://example.invalid}{x}',r'\def\x{x}\x',r'\includegraphics{x}',r'\htmlStyle{color:red}{x}',r'\begin{matrix}1\end{matrix}','{'*17+'x'+'}'*17,'x'*513,r'\frac{x}{',r'$x$']:
            with self.subTest(tex=tex),self.assertRaises(ValueError): validate_tex(tex)
    def test_pdf_preserves_text_images_and_privacy(self):
        body='## 原理\n'+r'由 \(n\lambda=2d\sin\theta\) 得到晶面间距。'+'\n'+r'\[D=\frac{K\lambda}{\beta\cos\theta}\]'+'\n正文结束。'
        with patch('reportlab.lib.utils.rlUrlRead',side_effect=AssertionError('No URLs allowed')):
            raw=s.pdf_bytes('排版测试',body,metadata={'name':'虚构测试姓名'})
        reader=PdfReader(io.BytesIO(raw))
        self.assertEqual(len(reader.pages),1)
        self.assertIn('正文结束',reader.pages[0].extract_text())
        self.assertIn('虚构测试姓名',reader.pages[0].extract_text())
        self.assertNotIn('虚构测试姓名',str(reader.metadata))
        images=[obj.get_object() for obj in reader.pages[0]['/Resources']['/XObject'].values() if obj.get_object().get('/Subtype')=='/Image']
        self.assertEqual(len(images),2)
    def test_pdf_rejects_bad_or_excessive_math(self):
        for body in [r'\[\input{secret}\]',r'\[\frac{1}\]',r'\[x^{\unknown}\]',r'未闭合 \(x',r'\[\text{中文}\]',((r'\[x\]'+'\n')*65),r'\['+'+'.join(['x']*110)+r'\]']:
            with self.subTest(body=body),self.assertRaises(ValueError): s.pdf_bytes('排版测试',body)
    def test_worker_rejects_batch_and_syntax(self):
        for formulas in [[],['x']*65,[r'\write18{cmd}'],['{x']]:
            with self.assertRaises(ValueError):s.isolated_parse('math',json.dumps(formulas).encode())

A4_WIDTH=453.55
if __name__=='__main__':unittest.main()
