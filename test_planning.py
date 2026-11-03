import json,copy
from pathlib import Path
from types import SimpleNamespace
import pytest
import pipeline as p
from planning import validate_plan,build_plan,checked_plan,presentation_with_plan,render_action_plan
from planning_schemas import ActionPlan
from schemas import Review,Report,Claim,Slide


def sample():
    root=Path(__file__).parent/'examples'
    plan=ActionPlan.model_validate_json((root/'action-plan-plan.json').read_text(encoding='utf-8'))
    facts=json.loads((root/'action-plan-facts.json').read_text(encoding='utf-8'))
    return plan,facts


def seed(tmp_path):
    plan,facts=sample()
    report=Report(title='Contoh inventaris',summary=[Claim(text='Pencatatan inventaris belum seragam.',fact_ids=['F0001'])],decisions=[],actions=[],uncertainties=[],slides=[Slide(title='Masalah inventaris',bullets=[Claim(text='Pencatatan inventaris belum seragam.',fact_ids=['F0001'])],notes='Sumber rekaan untuk uji.')])
    for name,value in [('report.json',report.model_dump()),('facts.json',facts),('review.json',{'passed':True,'issues':[]})]:p.write_json(tmp_path/name,value)
    return plan,facts

class FakeAI:
    def __init__(self,answers,used=0):self.answers=iter(answers);self.calls=[];self.journal=SimpleNamespace(data={'requests':[{}]*used})
    def ask(self,schema,instruction,payload,max_tokens=6000):
        self.calls.append(schema);self.journal.data['requests'].append({});return next(self.answers)


def test_valid_plan_preserves_relative_schedule_and_proposed_roles():
    plan,facts=sample();validate_plan(plan,facts)
    assert all(t.start_week>=1 and t.owner_role for t in plan.tasks)

@pytest.mark.parametrize('change,reason',[
    ('missing_fact','fakta'),('cycle','melingkar'),('overlap','prasyarat'),('missing_recommendation','rekomendasi'),('outside_horizon','52 minggu'),('duplicate','ganda')])
def test_invalid_plans_are_rejected(change,reason):
    plan,facts=sample()
    if change=='missing_fact':plan.tasks[0].fact_ids=['F9999']
    elif change=='cycle':plan.tasks[0].depends_on=['A002']
    elif change=='overlap':plan.tasks[1].start_week=1
    elif change=='missing_recommendation':plan.tasks[0].recommendation_id='R999'
    elif change=='outside_horizon':plan.tasks[-1].start_week=52
    elif change=='duplicate':plan.tasks[1].id=plan.tasks[0].id
    with pytest.raises(ValueError,match=reason):validate_plan(plan,facts)


def test_two_calls_then_cached_resume_without_changing_factual_report(tmp_path):
    plan,facts=seed(tmp_path);before=(tmp_path/'report.json').read_bytes()
    ai=FakeAI([plan,Review(passed=True,issues=[])])
    result,review=build_plan(tmp_path,lambda **kw:None,ai)
    assert len(ai.calls)==2 and review.passed and checked_plan(tmp_path)
    build_plan(tmp_path,lambda **kw:None,ai)
    assert len(ai.calls)==2 and before==(tmp_path/'report.json').read_bytes()
    merged=presentation_with_plan(tmp_path)
    data=json.loads(merged.read_text(encoding='utf-8'))
    assert len(data['slides'])>1 and data['slides'][1]['proposal']
    assert before==(tmp_path/'report.json').read_bytes()


def test_one_revision_then_draft_no_endless_loop(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_AI_REVISIONS','99')
    plan,facts=seed(tmp_path)
    ai=FakeAI([plan,Review(passed=False,issues=['R001 perlu scope lebih jelas']),plan,Review(passed=False,issues=['R001 tetap belum pasti'])])
    _,review=build_plan(tmp_path,lambda **kw:None,ai)
    assert len(ai.calls)==4 and not review.passed


def test_budget_reserves_plan_and_audit_as_pair(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_PAID_CALLS_PER_JOB','2');seed(tmp_path)
    ai=FakeAI([],used=1)
    with pytest.raises(ValueError,match='Sisa batas'):build_plan(tmp_path,lambda **kw:None,ai)
    assert not ai.calls


def test_changed_source_blocks_previously_audited_proposals(tmp_path):
    plan,facts=seed(tmp_path)
    build_plan(tmp_path,lambda **kw:None,FakeAI([plan,Review(passed=True,issues=[])]))
    (tmp_path/'report.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='berubah'):presentation_with_plan(tmp_path)


def test_excel_export_is_local_and_expected_file_is_created(tmp_path,monkeypatch):
    plan,facts=seed(tmp_path);build_plan(tmp_path,lambda **kw:None,FakeAI([plan,Review(passed=True,issues=[])]))
    monkeypatch.setattr(p,'AI',lambda *a:pytest.fail('No paid AI while exporting'))
    render_action_plan(tmp_path)
    import zipfile,xml.etree.ElementTree as E
    with zipfile.ZipFile(tmp_path/'action-plan.xlsx') as z:
        assert z.testzip() is None
        root=E.fromstring(z.read('xl/workbook.xml'))
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        assert [s.attrib['name'] for s in root.findall('.//s:sheet',ns)]==['Ringkasan','Rekomendasi','Action Plan','Timeline','Asumsi']
        action=E.fromstring(z.read('xl/worksheets/sheet3.xml'))
        assert action.findall('.//s:f',ns)
        assert action.find('.//s:dataValidations',ns) is not None


def test_plan_node_is_between_quality_and_render():
    w=json.loads((Path(__file__).parent/'n8n-workflow.json').read_text(encoding='utf-8'))
    n={node['id']:node for node in w['nodes']}
    assert '/stages/plan' in n['plan-start']['parameters']['url']
    assert w['connections'][n['quality-done']['name']]['main'][0][0]['node']==n['output-choice']['name']
    assert w['connections'][n['plan-done']['name']]['main'][0][0]['node']==n['render-start']['name']


def test_plan_stage_then_local_exports_reuse_plan_without_more_ai(tmp_path,monkeypatch):
    plan,facts=seed(tmp_path)
    meta={'input_kind':'text','title':'Test','slide_count':0,'extension':'.txt','planning_version':1,'completed_stages':['transcribe','summarize','quality'],'stage_seconds':{}}
    p.write_json(tmp_path/'job.json',meta)
    ai=FakeAI([plan,Review(passed=True,issues=[])])
    monkeypatch.setattr(p,'AI',lambda *a:ai)
    def update(**values):meta.update(values);p.write_json(tmp_path/'job.json',meta)
    p.run_stage(tmp_path,'plan',update)
    assert meta['completed_stages'][-1]=='plan' and len(ai.calls)==2
    p.run_stage(tmp_path,'render',update)
    assert len(ai.calls)==2 and meta['status']=='completed'
    assert all((tmp_path/name).exists() for name in ['summary.docx','action-plan.xlsx','presentation.pptx'])
    assert meta['completed_stages']==list(p.STAGES)


def test_new_upload_enables_plan_unless_explicitly_disabled(tmp_path,monkeypatch):
    import app,io
    from fastapi import UploadFile
    from test_auto_slides import upload,finish_immediate
    monkeypatch.setattr(app,'DATA',tmp_path)
    monkeypatch.setenv('ENABLE_ACTION_PLAN','1')
    result=finish_immediate(app.submit(file=upload(b'Tes diskusi.'),title='Tes',slide_count=0,orchestrator='n8n'))
    assert result['planning_version']==1
