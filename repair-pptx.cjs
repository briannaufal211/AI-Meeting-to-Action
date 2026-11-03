// Remove only orphan slide-master content-type declarations emitted by this
// PptxGenJS version. Existing parts, text, layouts and relationships are untouched.
const fs=require('fs');
const JSZip=require('jszip');
async function repairMasterTypes(filename){
 const zip=await JSZip.loadAsync(fs.readFileSync(filename));
 const part=zip.file('[Content_Types].xml');
 if(!part)throw Error('PPTX tidak memiliki [Content_Types].xml');
 const xml=await part.async('string');
 let removed=0;
 const clean=xml.replace(/<Override\b[^>]*PartName="(\/ppt\/slideMasters\/slideMaster\d+\.xml)"[^>]*\/>/g,(tag,name)=>{
  if(zip.file(name.slice(1)))return tag;
  removed++;return '';
 });
 if(removed){zip.file('[Content_Types].xml',clean);fs.writeFileSync(filename,await zip.generateAsync({type:'nodebuffer',compression:'DEFLATE'}));}
 return removed;
}
module.exports={repairMasterTypes};
