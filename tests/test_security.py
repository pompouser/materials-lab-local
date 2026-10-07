import base64
import io
import json
import sys
import threading
import unittest
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

def bet():
    return {'experiment':3,'metadata':{'name':'隐私测试姓名','studentId':'TEST-STUDENT-42','group':'07','date':'2026-10-07'},
        'rows':[{'relative_pressure':x,'uptake_cm3_STP_g':80*60*x/((1-x)*(1+59*x)), 'email':'private@example.invalid'} for x in [.05,.1,.2,.3]],
        'process':'隐私测试姓名 实际进行样品脱气并在稳定后记录数据。学号：TEST-STUDENT-42 邮箱：private@example.invalid',
        'figureDescriptions':['TEST-STUDENT-42 的实验数据']}

class PrivacyTests(unittest.TestCase):
    def test_prompt_excludes_identity_and_extra_columns(self):
        prompt=s.make_prompt(bet())
        for private in ['隐私测试姓名','TEST-STUDENT-42','private@example.invalid','2026-10-07','"个人信息":']:
            self.assertNotIn(private,prompt)
        self.assertIn('实际进行样品脱气',prompt)
        self.assertIn('已核验文献',prompt)
    def test_restore_equivalent_unknown_rows_not_forwarded(self):
        rows=s.validate_rows(s.experiment(3),bet()['rows'])
        self.assertEqual(set(rows[0]),set(s.experiment(3)['columns']))
        with self.assertRaises(ValueError): s.validate_rows(s.experiment(3),[{'relative_pressure':{},'uptake_cm3_STP_g':5}])
    def test_cloud_consent_required_before_network(self):
        with patch.object(s,'build_opener') as opener:
            with self.assertRaises(ValueError): s.cloud_generate({**bet(),'apiKey':'test-only-key'})
            opener.assert_not_called()
    def test_cloud_payload_and_destination(self):
        captured=[]
        class Reply(io.BytesIO): pass
        class Client:
            def open(self,request,timeout):
                captured.append(request)
                return Reply(json.dumps({'choices':[{'message':{'content':'仅用于测试的报告'}}]}).encode())
        with patch.object(s,'build_opener',return_value=Client()):
            answer=s.cloud_generate({**bet(),'cloudConsent':True,'apiKey':'test-only-key'})
        self.assertEqual(answer['text'],'仅用于测试的报告')
        self.assertEqual(captured[0].full_url,'https://api.deepseek.com/chat/completions')
        body=captured[0].data.decode()
        self.assertNotIn('TEST-STUDENT-42',body)
        self.assertNotIn('test-only-key',body)
        self.assertIsNone(s.NoRedirect().redirect_request(None,None,None,None,None,None))
    def test_parser_timeout(self):
        with patch.object(s.subprocess,'run',side_effect=subprocess.TimeoutExpired('parser',15)):
            with self.assertRaisesRegex(ValueError,'15 秒'): s.isolated_parse('pdf',b'%PDF-')
        self.assertTrue(s.PARSER_SLOTS.acquire(blocking=False));s.PARSER_SLOTS.release()
    def test_image_normalization_removes_metadata(self):
        target=io.BytesIO(); image=Image.new('RGB',(20,20),'white')
        exif=Image.Exif();exif[315]='private author';image.save(target,format='JPEG',exif=exif)
        result=s.isolated_parse('image',target.getvalue())
        cleaned=Image.open(io.BytesIO(base64.b64decode(result['data'].split(',')[1])))
        self.assertEqual(cleaned.size,(20,20));self.assertFalse(cleaned.getexif());self.assertNotIn('exif',cleaned.info)
    def test_image_dimension_budget(self):
        target=io.BytesIO();Image.new('RGB',(2001,1000),'white').save(target,format='PNG')
        with self.assertRaises(ValueError): s.isolated_parse('image',target.getvalue())
    def test_data_uri_injection_and_mime_rejected(self):
        for value in ['data:image/png;base64,AA\"><form>','data:image/jpeg;base64,'+base64.b64encode(b'%PDF-1.4').decode()]:
            with self.assertRaises(ValueError): s.decode_upload(value,'image/(?:png|jpeg)',4*1024*1024)
    def test_pdf_valid_and_page_budget(self):
        raw=s.pdf_bytes('过程描述','实际实验过程：样品充分脱气后依次测量压力点，稳定后记录数据并核对单位。')
        self.assertIn('实际实验过程',s.isolated_parse('pdf',raw)['text'])
        writer=PdfWriter()
        for _ in range(21):writer.add_blank_page(width=100,height=100)
        target=io.BytesIO();writer.write(target)
        with self.assertRaisesRegex(ValueError,'20 页'):s.isolated_parse('pdf',target.getvalue())
    def test_pdf_decompression_budget(self):
        writer=PdfWriter();page=writer.add_blank_page(width=100,height=100)
        stream=DecodedStreamObject();stream.set_data(b' '* (2*1024*1024+1))
        page[NameObject('/Contents')]=writer._add_object(stream.flate_encode())
        target=io.BytesIO();writer.write(target)
        with self.assertRaises(ValueError):s.isolated_parse('pdf',target.getvalue())

class LocalHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous=s.PORT;cls.server=s.LocalServer(('127.0.0.1',0),s.Handler)
        s.PORT=cls.server.server_address[1];cls.url=f'http://127.0.0.1:{s.PORT}'
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.worker.join();s.PORT=cls.previous
    def request(self,path,body=None,headers=None):
        actual={'Content-Type':'application/json','X-Lab-Token':s.TOKEN}
        actual.update(headers or {})
        request=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=actual)
        try:
            with urlopen(request,timeout=3) as r:return r.status,r.headers,r.read()
        except HTTPError as r:return r.code,r.headers,r.read()
    def test_browser_origin_and_token_gates(self):
        self.assertEqual(self.request('/api/curriculum',headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(self.request('/api/curriculum',headers={'Host':'attacker.invalid'})[0],403)
        self.assertEqual(self.request('/api/draft',bet(),{'Origin':'https://attacker.invalid'})[0],403)
        self.assertEqual(self.request('/api/draft',bet(),{'X-Lab-Token':'invalid'})[0],403)
    def test_security_headers_and_file_containment(self):
        status,headers,_=self.request('/')
        self.assertEqual(status,200);self.assertIn("form-action 'none'",headers['Content-Security-Policy'])
        self.assertEqual(headers['Referrer-Policy'],'no-referrer');self.assertEqual(headers['Cache-Control'],'no-store')
        for path in ['/../server.py','/../.env','/../data/references.json']:self.assertEqual(self.request(path)[0],404)
    def test_invalid_json_structure(self):
        for value in [[],{'params':[]},{'process':'x'*18001},{'metadata':{'name':{}}}]:
            self.assertEqual(self.request('/api/prompt',value)[0],400)
    def test_private_filename_default_and_explicit_course_name(self):
        data={**bet(),'text':'## 1 实验过程\n这是用于测试隐私默认设置的实验过程与报告正文。','figures':[]}
        status,headers,_=self.request('/api/report.pdf',data)
        self.assertEqual(status,200);self.assertNotIn('TEST-STUDENT-42',headers['Content-Disposition'])
        status,headers,_=self.request('/api/report.pdf',{**data,'identifyingFilename':True})
        self.assertEqual(status,200);self.assertIn('TEST-STUDENT-42',headers['Content-Disposition'])

if __name__=='__main__':unittest.main()
