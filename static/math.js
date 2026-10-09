/* Local formula rendering. User text is always inserted through textContent. */
(function(root){
 'use strict';
 let catalog=[];
 function configure(values){catalog=[...values].sort((a,b)=>b.source.length-a.source.length);}
 function escaped(text,pos){let n=0;while(pos>0&&text[pos-1]==='\\'){n++;pos--;}return n%2===1;}
 function segments(text,known=true){
  const output=[];
  function plain(value){
   if(!value)return;
   if(known){let cursor=0;
    while(cursor<value.length){let match=null;
     for(const f of catalog){const pos=value.indexOf(f.source,cursor);if(pos>=0&&(!match||pos<match.pos))match={pos,f};}
     if(!match)break;
     if(match.pos>cursor)output.push({kind:'text',text:value.slice(cursor,match.pos)});
     output.push({kind:'math',tex:match.f.tex,display:match.f.display,source:match.f.source});cursor=match.pos+match.f.source.length;
    }value=value.slice(cursor);
   }if(value)output.push({kind:'text',text:value});
  }
  let cursor=0,start=0;
  const delimiters=[['\\[','\\]',true],['\\(','\\)',false],['$$','$$',true],['$','$',false]];
  while(cursor<text.length){let matched=false;
   for(const [opening,closing,display] of delimiters){
    if(!text.startsWith(opening,cursor)||escaped(text,cursor))continue;
    if(opening==='$'&&(text.startsWith('$$',cursor)||(cursor&&text[cursor-1]==='$')))continue;
    let end=text.indexOf(closing,cursor+opening.length);
    while(end>=0&&(escaped(text,end)||(opening==='$'&&(text.startsWith('$$',end)||text[end-1]==='$'))))end=text.indexOf(closing,end+closing.length);
    if(end<0)continue;
    const tex=text.slice(cursor+opening.length,end).trim();
    if(!tex||(opening==='$'&&(tex.includes('\n')||!/[A-Za-z\\=^_{}+*/<>−-]/.test(tex))))continue;
    plain(text.slice(start,cursor));output.push({kind:'math',tex,display});cursor=end+closing.length;start=cursor;matched=true;break;
   }if(!matched)cursor++;
  }plain(text.slice(start));return output;
 }
 function append(target,part){
  if(part.kind==='text'){target.append(document.createTextNode(part.text));return;}
  const span=document.createElement('span');span.className=part.display?'math-block':'math-inline';
  if(part.source)span.title='原文：'+part.source;
  try{
   if(part.tex.length>512)throw Error('公式过长');
   root.katex.render(part.tex,span,{displayMode:part.display,throwOnError:true,trust:false,strict:'ignore',maxSize:8,maxExpand:100,macros:{},output:'htmlAndMathml'});
  }catch(_){span.className+=' math-error';span.textContent=(part.display?'\\[':'\\(')+part.tex+(part.display?'\\]':'\\)');span.title='公式语法无效或超出本地排版范围，已保留原文';}
  target.append(span);
 }
 function renderText(target,text){target.replaceChildren();for(const part of segments(text))append(target,part);}
 function preview(target,text){
  target.replaceChildren();if(!text.trim()){target.textContent='编辑正文后在这里查看公式与段落排版。';return;}
  let line=null,count=0;
  const flush=()=>{if(line&&line.hasChildNodes())target.append(line);line=null;};
  for(const part of segments(text)){
   if(part.kind==='text'){
    const lines=part.text.split('\n');lines.forEach((value,i)=>{if(i)flush();if(!value)return;
     const heading=!line&&/^#+\s*/.test(value);if(!line)line=document.createElement(heading?'h3':'p');
     line.append(document.createTextNode(value.replace(/^#+\s*/,'').replace(/\*\*/g,'')));
    });
   }else{
    count++;
    if(count>64){if(!line)line=document.createElement('p');line.append(document.createTextNode('\\('+part.tex+'\\)'));continue;}
    if(part.display){flush();append(target,part);}else{if(!line)line=document.createElement('p');append(line,part);}
   }
  }flush();
 }
 const api={configure,segments,renderText,preview};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LabMath=api;
})(typeof window==='undefined'?globalThis:window);
