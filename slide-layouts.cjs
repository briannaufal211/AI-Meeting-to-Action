/* Editable, content-led slide layouts. No AI API calls in this module. */
const fs=require('fs'),path=require('path'),PptxGenJS=require('pptxgenjs');
const W=13.333333,H=7.5;
const C={dark:'101B24',paper:'F4F0E8',white:'FFFFFF',ink:'172C36',muted:'58676E',copper:'A46337',line:'C9CDCB'};
function wrap(text,max){
 const result=[];
 for(const paragraph of String(text||'').split('\n')){
  let line='';
  for(const word of paragraph.split(/\s+/).filter(Boolean)){
   if(line&&line.length+word.length+1>max){result.push(line);line='';}
   if(word.length>max){if(line){result.push(line);line='';}for(let n=0;n<word.length;n+=max)result.push(word.slice(n,n+max));}
   else line+=(line?' ':'')+word;
  }
  if(line)result.push(line);
 }
 return result.length?result:[''];
}
// Conservative wrapping leaves space for wider glyphs and bold font metrics.
const limit=(w,size)=>Math.max(8,Math.floor(w*6.3*20/size));
const leading=size=>size/72*1.24;
const textH=(t,w,size)=>wrap(t,limit(w,size)).length*leading(size)+.07;
function concise(text,max=160){const value=String(text);if(value.length<=max)return value;const cut=value.slice(0,max);return cut.slice(0,Math.max(cut.lastIndexOf(' '),max-20))+'…';}
function header(src){const lines=wrap(src.title,limit(11.8,32));return {lines,titleH:lines.length*leading(32)+.06,bodyY:.8+lines.length*leading(32)+.48};}
function selectLayout(src,index){
 if(['recommendation','timeline','action_table'].includes(src.layout))return src.layout;
 if(src.layout&&src.layout!=='auto')return src.layout;
 if(index===0&&src.title.length<85&&src.bullets.length<=2&&src.bullets.reduce((n,b)=>n+b.text.length,0)<210)return 'cover';
 if(/ringkasan|inti|utama|fokus|overview/i.test(src.title))return 'overview';
 if(/risiko|kendala|hambatan|belum pasti/i.test(src.title))return 'risk';
 if(/keputusan|persetujuan/i.test(src.title))return 'decisions';
 if(/tindak lanjut|pembagian tugas/i.test(src.title))return 'actions';
 return index%2?'findings':'overview';
}
function groupText(src,kind){
 const hd=header(src),available=6.25-hd.bodyY;
 const columns=(kind==='overview'||kind==='comparison'||kind==='process')&&src.bullets.length>=2;
 const width=columns?5.55:10.8;
 const maxLines=Math.max(1,Math.floor((available-(columns?.95:.15))/leading(22)));
 const pieces=[];
 for(let n=0;n<src.bullets.length;n++){
  const b=src.bullets[n],lines=wrap(b.text,limit(width,22));
  for(let i=0;i<lines.length;i+=maxLines)pieces.push({...b,lines:lines.slice(i,i+maxLines),ordinal:n+1});
 }
 const pages=[];let items=[],used=0;
 const flush=()=>{if(items.length){pages.push({src,kind,items,hd,part:pages.length,columns});items=[];used=0;}};
 for(const item of pieces){
  const h=item.lines.length*leading(22)+.28;
  if(columns){if(items.length===2)flush();}
  else if(items.length&&used+h>available)flush();
  items.push(item);used+=h;
 }
 flush();return pages;
}
function buildPages(report){
 const pages=[];
 report.slides.forEach((src,index)=>{
  const kind=selectLayout(src,index);
  if(kind==='timeline'){
   const hd=header(src),capacity=6.25-hd.bodyY-.95;let items=[],height=0,part=0;
   for(const task of src.tasks){
    const rowHeight=Math.max(.64,textH(task.id+' '+task.slide_summary,4.5,17)+.14);
    if(items.length&&height+rowHeight>capacity){pages.push({src,kind,items,hd,part:part++});items=[];height=0;}
    items.push({...task,rowHeight});height+=rowHeight;
   }
   if(items.length)pages.push({src,kind,items,hd,part});
  }else if(kind==='action_table'){
   let batch=[],height=0;const hd=header(src),capacity=6.25-hd.bodyY-.55;
   for(const task of src.tasks){
    const display_deliverable=concise(task.deliverable);
    const h=Math.max(textH(task.id+' '+task.slide_summary,4.35,19),textH(task.owner_role+'\nMinggu '+task.start_week+'-'+(task.start_week+task.duration_weeks-1),2.65,18),textH(display_deliverable,3.55,18))+.25;
    if(h>capacity)throw Error('Satu tugas terlalu panjang untuk tabel slide; perpendek ringkasan/keluaran. Rincian tetap tersimpan di Excel.');
    if(batch.length&&height+h>capacity){pages.push({src,kind,items:batch,hd,part:pages.filter(p=>p.src===src).length});batch=[];height=0;}
    batch.push({...task,display_deliverable,rowHeight:h});height+=h;
   }
   if(batch.length)pages.push({src,kind,items:batch,hd,part:pages.filter(p=>p.src===src).length});
  }else if(kind==='recommendation'){
   const r=src.recommendation,hd=header(src),available=6.25-hd.bodyY;
   if(textH(r.problem,3.4,21)+.5<available&&textH(r.slide_summary,7.3,26)+textH(r.benefit,7.3,20)+1.15<available)pages.push({src,kind,items:src.bullets,hd,part:0});
   else pages.push(...groupText(src,'findings'));
  }else if(kind==='cover'&&src.title.length<85&&src.bullets.reduce((n,b)=>n+b.text.length,0)<210&&wrap(src.title,limit(7.1,40)).length<=3){
   pages.push({src,kind,items:src.bullets.map((b,n)=>({...b,ordinal:n+1})),hd:header(src),part:0});
  }else pages.push(...groupText(src,kind==='cover'?'overview':kind));
 });
 return pages;
}
async function renderPresentation(input,output){
 const report=JSON.parse(fs.readFileSync(input,'utf8').replace(/^\uFEFF/,''));
 const folder=path.dirname(input),rp=path.join(folder,'review.json');
 const review=fs.existsSync(rp)?JSON.parse(fs.readFileSync(rp,'utf8')):null;
 const currentAudit=fs.existsSync(path.join(folder,'quality-manifest.json'));
 const qualityLabel=report.demo?'CONTOH DESAIN / DATA REKAAN':review?(review.passed&&currentAudit?'DIPERIKSA TERHADAP TRANSKRIP':review.passed?'DRAF / AUDIT KONTEKS BELUM DIJALANKAN':'DRAF / PERLU KONFIRMASI'):'';
 const pptx=new PptxGenJS();pptx.layout='LAYOUT_WIDE';pptx.author='Otomasi Diskusi Lokal';pptx.title=report.title;pptx.subject=report.title;pptx.lang='id-ID';
 pptx.theme={headFontFace:'Arial Narrow',bodyFontFace:'Arial',lang:'id-ID'};
 const pages=buildPages(report),geometry=[];
 function tx(s,t,x,y,w,h,size=22,opts={}){
  if(x<0||y<0||x+w>W+.02||y+h>H+.02)throw Error('Teks di luar batas slide: '+String(t).slice(0,55));
  geometry.push({slide:s._slideNum,x,y,w,h,size});
  s.addText(t,{x,y,w,h,fontFace:'Arial',fontSize:size,color:C.ink,margin:0,breakLine:false,valign:'top',...opts});
 }
 function line(s,x,y,w,color=C.line){s.addShape(pptx.ShapeType.line,{x,y,w,h:0,line:{color,width:.8}});}
 function text(s,t,x,y,w,size=22,opts={}){const lines=wrap(t,limit(w,size));tx(s,lines.join('\n'),x,y,w,lines.length*leading(size)+.07,size,opts);return lines.length*leading(size)+.07;}
 function footer(s,p,i){
  const dark=p.kind==='cover',ink=dark?'B0B8BB':C.muted;
  const refs=[...new Set(p.items.flatMap(b=>b.fact_ids||[]))];
  const proposal=report.demo?'CONTOH DESAIN / DATA REKAAN':p.src.proposal?(p.src.plan_review_passed&&review?.passed?'USULAN AI / MEMERLUKAN PERSETUJUAN':'DRAF USULAN / PERLU KONFIRMASI'):qualityLabel;
  line(s,.7,6.65,11.9,dark?'31444C':C.line);
  if(proposal)tx(s,proposal,.7,6.79,10.9,.20,9,{color:ink,bold:true});
  const source=report.demo?'MATERI REKAAN UNTUK CONTOH DESAIN':refs.length?'Rujukan '+refs.slice(0,7).join(', ')+(refs.length>7?' dan lainnya di catatan':''):'';
  tx(s,source,.7,7.05,10.8,.21,9,{color:ink});tx(s,`${i+1} / ${pages.length}`,11.6,7.05,1,.21,10,{color:ink,align:'right'});
  s.addNotes([p.src.notes||'',qualityLabel,p.src.proposal?'Rekomendasi, peran, durasi dan timeline adalah usulan yang memerlukan persetujuan.':'',
   'Rujukan fakta: '+refs.join(', '),'Ketidakpastian: '+(report.uncertainties||[]).join('; '),
   ...(p.src.tasks||[]).map(t=>`${t.id}: ${t.task}. Peran usulan ${t.owner_role}. Minggu ${t.start_week}-${t.start_week+t.duration_weeks-1}. Keluaran ${t.deliverable}. Penerimaan ${t.acceptance}. Prasyarat ${(t.depends_on||[]).join(', ')||'Tidak ada'}.`),
   p.src.recommendation?'Rincian rekomendasi: '+JSON.stringify(p.src.recommendation):'', 'Public edition: neutral editable layouts; no personal reference assets.']);
 }
 pages.forEach((p,i)=>{
  const s=pptx.addSlide();s.background={color:p.kind==='cover'?C.dark:C.paper};
  if(p.kind==='cover'){
   const asset=path.join(__dirname,'assets','optional-cover.png');
   if(fs.existsSync(asset))s.addImage({path:asset,x:8.55,y:0,w:677/941*6.65,h:6.65,sizing:{type:'cover',w:4.783333,h:6.65},altText:'Optional cover image supplied locally by the user'});
   tx(s,'HASIL DISKUSI',.75,.62,7.2,.3,12,{color:'D49C70',bold:true,charSpacing:1.2});
   const title=wrap(p.src.title,limit(7.1,40));tx(s,title.join('\n'),.7,1.45,7.15,title.length*leading(40)+.1,40,{fontFace:'Arial Narrow',bold:true,color:C.paper});
   let y=1.45+title.length*leading(40)+.45;
   for(const b of p.items)y+=text(s,b.text,.75,y,7.05,22,{color:C.paper})+.16;
  }else{
   tx(s,p.src.proposal?'REKOMENDASI DAN RENCANA USULAN':'HASIL DISKUSI',.7,.36,11.8,.25,11,{color:C.copper,bold:true,charSpacing:.7});
   tx(s,p.hd.lines.join('\n'),.7,.8,11.9,p.hd.titleH,32,{fontFace:'Arial Narrow',bold:true});
   if(p.part)tx(s,'Lanjutan',11.2,.37,1.4,.23,10,{color:C.muted,align:'right'});
   const y=p.hd.bodyY;
   if(p.kind==='recommendation'){
    const r=p.src.recommendation;
    tx(s,'Masalah sumber',.7,y,3.4,.35,15,{color:C.copper,bold:true});text(s,r.problem,.7,y+.5,3.4,21);
    tx(s,'Pendekatan yang diusulkan',4.8,y,7.3,.35,15,{color:C.copper,bold:true});
    const hh=text(s,r.slide_summary,4.8,y+.5,7.5,26,{bold:true});
    tx(s,'Manfaat yang diharapkan',4.8,y+.5+hh+.18,7.4,.3,14,{color:C.copper,bold:true});text(s,r.benefit,4.8,y+.5+hh+.63,7.3,20);
   }else if(p.kind==='timeline'){
    const last=Math.max(...p.src.tasks.map(t=>t.start_week+t.duration_weeks-1));
    tx(s,'Estimasi minggu sejak persetujuan rencana',.7,y,11.9,.3,16,{color:C.muted});
    const chartX=5.65,chartW=6.15,rowY=y+.95,tickStep=Math.max(1,Math.ceil(last/8)),totalH=p.items.reduce((n,t)=>n+t.rowHeight,0);
    for(let week=1;week<=last;week+=tickStep){const x=chartX+(week-1)/last*chartW;tx(s,'M'+week,x,y+.5,.65,.26,12,{color:C.muted});s.addShape(pptx.ShapeType.line,{x,y:rowY-.1,w:0,h:totalH,line:{color:C.line,width:.5}});}
    let yy=rowY;
    p.items.forEach((t,n)=>{
     text(s,t.id+' '+t.slide_summary,.7,yy,4.5,17);
     const startX=chartX+(t.start_week-1)/last*chartW,bw=t.duration_weeks/last*chartW;
     s.addShape(pptx.ShapeType.rect,{x:startX,y:yy+.08,w:bw,h:.24,line:{color:C.copper,transparency:100},fill:{color:C.copper}});
     tx(s,`${t.start_week}-${t.start_week+t.duration_weeks-1}`,chartX+chartW+.13,yy,.7,.28,11,{color:C.muted});
     yy+=t.rowHeight;
    });
   }else if(p.kind==='action_table'){
    const rows=[[{text:'Langkah usulan',options:{bold:true}},{text:'Peran PIC dan jadwal',options:{bold:true}},{text:'Keluaran',options:{bold:true}}],...p.items.map(t=>[
     wrap(t.id+' '+t.slide_summary,limit(4.35,19)).join('\n'),wrap(t.owner_role+'\nMinggu '+t.start_week+'-'+(t.start_week+t.duration_weeks-1),limit(2.65,18)).join('\n'),wrap(t.display_deliverable,limit(3.55,18)).join('\n')])];
    s.addTable(rows,{x:.7,y,w:11.9,colW:[4.65,3,4.25],rowH:[.5,...p.items.map(t=>t.rowHeight)],fontFace:'Arial',fontSize:18,color:C.ink,fill:C.paper,margin:[5,8,5,8],border:{color:C.line,pt:.6},autoPage:false,valign:'top'});
   }else if(p.columns){
    p.items.forEach((b,n)=>{const x=.7+n*6.3;tx(s,String(b.ordinal).padStart(2,'0'),x,y,.7,.45,27,{color:C.copper,fontFace:'Arial Narrow',bold:true});line(s,x,y+.58,5.6);tx(s,b.lines.join('\n'),x,y+.87,5.55,b.lines.length*leading(22)+.07,22);});
   }else{
    let yy=y;p.items.forEach(b=>{tx(s,String(b.ordinal).padStart(2,'0'),.7,yy,.7,.45,26,{color:C.copper,fontFace:'Arial Narrow',bold:true});tx(s,b.lines.join('\n'),1.65,yy,10.8,b.lines.length*leading(22)+.07,22);yy+=b.lines.length*leading(22)+.28;});
   }
  }
  footer(s,p,i);
 });
 await pptx.writeFile({fileName:output});await require('./repair-pptx.cjs').repairMasterTypes(output);
 fs.writeFileSync(path.join(path.dirname(output),'presentation-layout.json'),JSON.stringify({version:4,paid_calls:0,slide_count:pages.length,slides:pages.map((p,i)=>({slide:i+1,title:p.src.title,layout:p.kind,continuation:p.part>0,item_count:p.items.length})),geometry},null,2));
}
module.exports={renderPresentation,buildPages,selectLayout,wrap};
