"""Render saved synthetic data locally; never constructs an AI client."""
from pathlib import Path
import shutil,json,subprocess,os
from reference_word import render_summary_docx
from excel_export import export
ROOT=Path(__file__).resolve().parent

def saved_example_presentation(out):
 # Editorial examples can deliberately contain null schedules. They are not
 # passed through the stricter schema used for newly generated AI proposals.
 report=json.loads((out/'report.json').read_text(encoding='utf-8'))
 plan=json.loads((out/'plan.json').read_text(encoding='utf-8'))
 def add(title,texts,refs):
  report['slides'].append({'title':title,'layout':'findings','proposal':True,
   'bullets':[{'text':t,'fact_ids':refs} for t in texts],
   'notes':'Contoh rekaan yang ditinjau editorial; bukan audit AI baru.'})
 for r in plan['recommendations']:
  add(r['priority']+' '+r['title'],[r['problem'],r['proposal'],'Manfaat usulan: '+r['benefit']],r['fact_ids'])
 for t in plan['tasks']:
  schedule=(f"Mulai minggu {t['start_week']}, durasi {t['duration_weeks']} minggu."
   if t.get('start_week') is not None and t.get('duration_weeks') is not None
   else 'Jadwal dan durasi belum dikonfirmasi.')
  add(t['id']+' '+t['phase'],[t['task'],'Peran PIC usulan: '+t['owner_role']+'. '+schedule,
   'Keluaran: '+t['deliverable'],'Penerimaan: '+t['acceptance']],t['fact_ids'])
 target=out/'presentation-report.json';target.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
 return target

if __name__=='__main__':
 src=ROOT/'examples/meeting-demo';out=ROOT/'data/example-export';out.mkdir(parents=True,exist_ok=True)
 for p in src.iterdir():
  if p.is_file():shutil.copyfile(p,out/p.name)
 read=lambda n:json.loads((out/n).read_text(encoding='utf-8'))
 render_summary_docx(out,read('report.json'),read('facts.json'),read('review.json'))
 subprocess.run([os.getenv('NODE_EXE','node'),str(ROOT/'render.cjs'),str(saved_example_presentation(out)),str(out/'presentation.pptx')],check=True)
 export(out,out/'action-plan.xlsx')
 print('Offline exports:',out)
