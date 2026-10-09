const test=require('node:test'), assert=require('node:assert/strict');
const p=require('../static/privacy.js');
const experiments=Array.from({length:10},()=>({columns:['batch','value']}));
const project=()=>({version:1,experiment:1,state:{metadata:{name:'虚构测试姓名',studentId:'TEST-ID',date:'',group:''},rows:[{batch:'test',value:-1.2}],params:{},figures:[],process:'过程',report:'报告',dataKind:'real'}});
test('spreadsheet formulas become text; scientific negative numbers retain numeric value',()=>{
  for(const value of ['=1+1','+SUM(1)','-HYPERLINK("x")','@SUM(1)','\t=1+1',' \r=1+1']) assert.ok(p.csvCell(value).includes("'"));
  for(const value of ['-1.2','-1e-3','+.25','3']) assert.equal(p.csvCell(value),value);
  assert.equal(p.csvCell('a,b'),'"a,b"');
});
test('chart formats are explicit and MIME mismatch is rejected',()=>{
  for(const [name,type,kind] of [['chart.PDF','application/pdf','pdf'],['chart.svg','image/svg+xml','svg'],['chart.png','','png'],['chart.jpg','image/jpeg','jpeg']])assert.equal(p.chartKind({name,type}),kind);
  for(const file of [{name:'x.html',type:'text/html'},{name:'x.svg',type:'text/html'},{name:'x.pdf',type:'image/png'}])assert.throws(()=>p.chartKind(file));
});
test('figure-only drafts retain chart notes in encrypted backup and old drafts remain compatible',async()=>{
  const source=project();source.state.rows=[];source.state.chartNotes='图1：用户记录的坐标、单位和结果。';
  const clean=p.cleanProject(source,experiments);assert.deepEqual(clean.state.rows,[]);assert.equal(clean.state.chartNotes,source.state.chartNotes);
  const password='test-only-password-42';const backup=await p.encrypt(clean,password);const restored=p.cleanProject(await p.decrypt(backup,password),experiments);assert.deepEqual(restored,clean);
  assert.equal(p.cleanProject(project(),experiments).state.chartNotes,'');
  source.state.chartNotes='x'.repeat(18001);assert.throws(()=>p.cleanProject(source,experiments));
});
test('project fields are allowlisted; credentials and extra CSV columns are dropped',()=>{
  const original=project();original.state.apiKey='test-only-key';original.state.rows[0].email='private@example.invalid';original.state.metadata.extra='secret';
  const clean=p.cleanProject(original,experiments);
  assert.equal(clean.state.apiKey,undefined);assert.equal(clean.state.rows[0].email,undefined);assert.equal(clean.state.metadata.extra,undefined);
  assert.equal(clean.state.metadata.studentId,'TEST-ID');
});
test('whole image URL grammar rejects HTML, SVG, paths and mismatched signatures',()=>{
  for(const value of ['data:image/png;base64,AA"><form>','data:image/svg+xml;base64,AAAA','file:///private','data:image/jpeg;base64,JVBERi0xLjQ=']) assert.throws(()=>p.imageURL(value));
});
test('original PDF survives cleaning, encryption and restoration byte for byte',async()=>{
  const source=project(),data='data:application/pdf;base64,'+Buffer.from('%PDF-1.4\nprivate-test-metadata\n%%EOF').toString('base64');
  source.state.notesPDF={data,pages:2,filename:'private-test-name.pdf',apiKey:'test-secret'};
  const clean=p.cleanProject(source,experiments);
  assert.deepEqual(clean.state.notesPDF,{data,pages:2});
  const restored=p.cleanProject(await p.decrypt(await p.encrypt(clean,'test-only-password-42'),'test-only-password-42'),experiments);
  assert.equal(restored.state.notesPDF.data,data);assert.equal(restored.state.process,'过程');
  assert.equal(p.cleanProject(project(),experiments).state.notesPDF,null);
});
test('PDF URLs and page counts are validated before restoring',()=>{
  for(const data of ['file:///private.pdf','data:text/html;base64,JVBERi0=','data:application/pdf;base64,AAAA','data:application/pdf;base64,JVBERi0=\"<form>'])assert.throws(()=>p.pdfURL(data));
  for(const pages of [0,21,true,'1']){
    const source=project();source.state.notesPDF={data:'data:application/pdf;base64,JVBERi0=',pages};
    assert.throws(()=>p.cleanProject(source,experiments));
  }
});
test('malformed nested state and oversized text fail without partial restoration',()=>{
  const input=project();input.state.rows=[{batch:{},value:5}];assert.throws(()=>p.cleanProject(input,experiments));
  input.state.rows=[];input.state.report='x'.repeat(18001);assert.throws(()=>p.cleanProject(input,experiments));
});
test('encrypted backup roundtrip hides identities; wrong password/tampering fail',async()=>{
  const password='test-only-password-42', original=project();
  const envelope=await p.encrypt(original,password);
  assert.ok(!JSON.stringify(envelope).includes('TEST-ID'));
  assert.deepEqual(await p.decrypt(envelope,password),original);
  await assert.rejects(p.decrypt(envelope,'wrong-test-password'));
  const corrupt={...envelope,ciphertext:'A'+envelope.ciphertext.slice(1)};
  if(corrupt.ciphertext===envelope.ciphertext)corrupt.ciphertext='B'+envelope.ciphertext.slice(1);
  await assert.rejects(p.decrypt(corrupt,password));
  await assert.rejects(p.encrypt(original,'short'));
});
