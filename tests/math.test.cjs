const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const math=require('../static/math.js');
const katex=require('../static/vendor/katex/katex.min.js');
const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/formulas.json'),'utf8'));
math.configure(catalog);
test('all 60 grounded course formulas render with local KaTeX and accessible MathML',()=>{
 for(const f of catalog){
  assert.equal(math.segments(f.source)[0].tex,f.tex);
  const html=katex.renderToString(f.tex,{throwOnError:true,trust:false,maxSize:8,maxExpand:100});
  assert.match(html,/katex-mathml/);assert.match(html,/annotation encoding="application\/x-tex"/);
 }
});
test('explicit delimiters, escaped markers and multiline blocks retain text',()=>{
 assert.deepEqual(math.segments(String.raw`中文 \(x^2\) 与 \[\frac{1}{2}\]`).filter(p=>p.kind==='math'),[
  {kind:'math',tex:'x^2',display:false},{kind:'math',tex:String.raw`\frac{1}{2}`,display:true}]);
 assert.equal(math.segments('$$\n'+String.raw`\int_0^1 x\,dx`+'\n$$')[0].display,true);
 for(const value of [String.raw`价格 $12 和 $18`,String.raw`未闭合 \(x`,String.raw`转义 \\(x\\)`,String.raw`只有 $$`])assert.deepEqual(math.segments(value,false),[{kind:'text',text:value}]);
});
test('local font URLs exist and unsafe commands cannot create links',()=>{
 const css=fs.readFileSync(path.join(__dirname,'../static/vendor/katex/katex.min.css'),'utf8');
 for(const [,url]of css.matchAll(/url\(([^)]+)\)/g)){assert(!/https?:/.test(url));assert(fs.existsSync(path.join(__dirname,'../static/vendor/katex',url)));}
 assert(!katex.renderToString(String.raw`\href{https://example.invalid}{x}`,{trust:false,throwOnError:false}).includes('href="https://'));
});
