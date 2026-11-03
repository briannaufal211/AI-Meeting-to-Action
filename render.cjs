const [input,output]=process.argv.slice(2);
if(!input||!output)throw Error('Usage: node render.cjs report.json output.pptx');
require('./slide-layouts.cjs').renderPresentation(input,output).catch(e=>{console.error(e.stack||e.message);process.exitCode=1;});
