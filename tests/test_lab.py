import io, math, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
from pypdf import PdfReader

def rows(n,values):
    return [dict(zip(s.experiment(n)['columns'],v)) for v in values]

class LaboratoryTests(unittest.TestCase):
    def test_curriculum_and_sources(self):
        self.assertEqual(sum(len(e['questions']) for e in s.CURRICULUM['experiments']),30)
        for n in range(1,11):
            self.assertGreaterEqual(len(s.references(n)),3)
            for ref in s.references(n):
                self.assertTrue(ref['url'].startswith('https://'))
                self.assertIn(ref['access'],('abstract','fulltext'))
    def test_mof(self):
        r=s.analyze(1,rows(1,[['A',100,80,130,12,40,50]]))
        self.assertAlmostEqual(r['results']['平均表观收率 (%)'],80)
    def test_scherrer(self):
        r=s.analyze(2,rows(2,[[25,10],[30,100],[35,10]]),{'fwhm_deg':.3,'instrument_deg':.1})
        expected=.89*.15405/(math.radians(math.sqrt(.09-.01))*math.cos(math.radians(15)))
        self.assertAlmostEqual(r['results']['Scherrer D (nm)'],expected)
        with self.assertRaises(ValueError):s.analyze(2,rows(2,[[30,100]]),{'fwhm_deg':.1,'instrument_deg':.2})
    def test_bet_known_parameters(self):
        C,nm=60,80; xs=[.05,.08,.1,.15,.2,.25,.3]
        data=rows(3,[[x,nm*C*x/((1-x)*(1+(C-1)*x))] for x in xs])
        result=s.analyze(3,data)['results']
        self.assertAlmostEqual(result['C'],C,places=8)
        self.assertAlmostEqual(result['nₘ (cm³ STP/g)'],nm,places=8)
        self.assertAlmostEqual(result['R²'],1)
    def test_dsc_time_conversion(self):
        r=s.analyze(4,rows(4,[[220,0],[230,1],[240,0]]),{'fit_min':220,'fit_max':240,'rate':10})
        self.assertAlmostEqual(r['results']['线性端点基线积分 ΔH (J/g)'],60)
    def test_ftir_percent(self):
        r=s.analyze(5,rows(5,[[1700,10],[2000,50]]))
        self.assertAlmostEqual(r['results']['对应吸光度'],1)
        with self.assertRaises(ValueError):s.analyze(5,rows(5,[[1700,0]]))
    def test_tga_interpolation(self):
        r=s.analyze(6,rows(6,[[30,100],[130,90],[400,10]]))
        self.assertAlmostEqual(r['results']['T5% (℃)'],80)
        self.assertAlmostEqual(r['results']['残余质量 (%)'],10)
    def test_tma_units(self):
        r=s.analyze(7,rows(7,[[30,0],[40,8],[50,16],[60,24]]),{'length_mm':16})
        self.assertAlmostEqual(r['results']['线膨胀系数 α (K⁻¹)'],50e-6)
    def test_photoelastic_stress_difference(self):
        r=s.analyze(8,rows(8,[[0,3,45,3,10]]))['results']['各测点'][0]
        self.assertAlmostEqual(r['主应力差 (MPa)'],10)
        self.assertAlmostEqual(r['σx−σy (MPa)'],0,places=10)
        self.assertAlmostEqual(r['τxy (MPa)'],5)
    def test_vdp_unequal_and_hall_offsets(self):
        rs=200; a=20; b=-rs/math.pi*math.log(1-math.exp(-math.pi*a/rs))
        # signal 1mV, constant 3mV, current-odd longitudinal 0.2mV
        voltages=[4.2,1.8,3.8,2.2]
        result=s.analyze(9,rows(9,[[1,.5,.1,*voltages,a,b]]))['results']['各次测量'][0]
        self.assertAlmostEqual(result['Rs (Ω/□)'],rs)
        self.assertAlmostEqual(result['RH (m³/C)'],.0002)
        self.assertAlmostEqual(result['ρ (Ω·m)'],.02)
    def test_four_probe_models_and_reversal(self):
        r=rows(10,[[1,10.3,-9.7,1,.1,1]])
        thin=s.analyze(10,r,{'geometry':'thin'})['results']['平均 ρ (Ω·m)']
        thick=s.analyze(10,r,{'geometry':'bulk'})['results']['平均 ρ (Ω·m)']
        self.assertAlmostEqual(thin,math.pi/math.log(2)*10*.0001)
        self.assertAlmostEqual(thick,2*math.pi*.001*10)
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):s.analyze(6,rows(6,[[30,'NaN'],[40,90]]))
    def test_prompt_grounding_and_missing_process(self):
        d={'experiment':3,'rows':rows(3,[[x,80*60*x/((1-x)*(1+59*x))] for x in [.05,.1,.2,.3]]),'process':'实际过程说明：样品脱气后按规定压力依次测量，达到稳定判据再读数。','dataKind':'simulation'}
        text=s.make_prompt(d)
        self.assertIn('教学模拟',text)
        self.assertIn('讨论题及辅导答案',text)
        self.assertIn('已核验文献',text)
        d['process']=''
        with self.assertRaises(ValueError):s.make_prompt(d)
    def test_pdf_layout_and_limit(self):
        data=s.pdf_bytes('测试报告','## 1 结果\nPET 质量为 5 mg，数据只是排版测试。')
        reader=PdfReader(io.BytesIO(data));self.assertEqual(len(reader.pages),1)
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width),595.2756,places=3)
        self.assertIn('PET',reader.pages[0].extract_text())
        with self.assertRaises(s.PageLimit):s.pdf_bytes('页数测试','\n'.join(['这里是用于验证页数限制的长段落。'*10]*100))

if __name__=='__main__':unittest.main()
