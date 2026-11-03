import json
from pathlib import Path
import pytest
import pipeline as p
from schemas import SummaryReport,Claim,Review,Report

def test_summary_only_render_never_enters_ppt_or_plan(tmp_path,monkeypatch):
 p.write_json(tmp_path/'job.json',{'output_mode':'summary_only','planning_version':1,'quality_version':0,'completed_stages':['transcribe','summarize','quality'],'stage_seconds':{},'slide_count':-1})
 report=SummaryReport(title='Ringkasan',summary=[Claim(text='Uji.',fact_ids=['F0001'])],decisions=[],actions=[],uncertainties=[],slides=[])
 p.write_json(tmp_path/'report.json',report.model_dump());p.write_json(tmp_path/'review.json',Review(passed=True,issues=[]).model_dump());p.write_json(tmp_path/'facts.json',[{'id':'F0001','text':'Uji.','quote':'Uji.','source_ids':['S00001']}])
 for name in ['render_pptx','build_plan','render_action_plan','AI']:monkeypatch.setattr(p,name,lambda *a,**kw:pytest.fail('Forbidden in summary-only local export'))
 values={};p.run_stage(tmp_path,'render',lambda **kw:values.update(kw))
 assert (tmp_path/'summary.docx').exists() and not (tmp_path/'presentation.pptx').exists()
 assert values['status']=='completed'

def test_summary_preflight_has_no_ppt_dependency(tmp_path,monkeypatch):
 p.write_json(tmp_path/'job.json',{'output_mode':'summary_only'})
 monkeypatch.setattr(p,'render_pptx',lambda *a:pytest.fail('No PPT preflight for summary'))
 p.local_preflight(tmp_path)
 assert json.loads((tmp_path/'preflight.json').read_text())['word_local_ok']
 assert not (tmp_path/'summary.docx').exists()

def test_empty_slides_only_permitted_for_summary_mode():
 report=SummaryReport(title='T',summary=[Claim(text='Uji',fact_ids=['F1'])],decisions=[],actions=[],uncertainties=[],slides=[])
 p.validate_slide_count(report,-1)
 with pytest.raises(ValueError):p.validate_slide_count(report,0)

def test_new_job_summary_choice_never_queues_audio_when_orchestrated(tmp_path,monkeypatch):
 import app
 from test_auto_slides import upload,finish_immediate
 monkeypatch.setattr(app,'DATA',tmp_path)
 result=finish_immediate(app.submit(file=upload(b'Uji.'),title='Tes',slide_count=10,orchestrator='n8n',output_mode='summary_only'))
 assert result['planning_version']==0 and result['slide_count']==-1 and result['output_mode']=='summary_only'
 assert result['status']=='waiting'

def test_changing_mode_does_not_execute(tmp_path,monkeypatch):
 import app,uuid
 monkeypatch.setattr(app,'DATA',tmp_path);jid=str(uuid.uuid4());folder=tmp_path/jid;folder.mkdir()
 p.write_json(folder/'job.json',{'id':jid,'title':'T','filename':'test.txt','created_at':'2026-11-02T00:00:00Z','status':'waiting','completed_stages':['transcribe'],'output_mode':'summary_only','orchestrator':'n8n','stage':'transcribe_done','progress':60})
 monkeypatch.setattr(app.TASKS,'put',lambda *a:pytest.fail('Choice must not enqueue'))
 app.set_output_mode(jid,'summary_ppt')
 j=json.loads((folder/'job.json').read_text());assert j['planning_version']==1 and j['output_mode']=='summary_ppt'

def test_graph_has_summary_bypass_and_no_file_required_for_reuse():
 w=json.loads((Path(__file__).parent/'n8n-workflow.json').read_text(encoding='utf-8'));n={v['id']:v for v in w['nodes']}
 assert w['connections']['Perlu PowerPoint?']['main'][1][0]['node']==n['render-start']['name']
 assert w['connections']['Perlu PowerPoint?']['main'][0][0]['node']==n['plan-start']['name']
