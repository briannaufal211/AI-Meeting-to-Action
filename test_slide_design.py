"""Offline presentation regression checks, including complete plan coverage."""
import json,subprocess,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import pipeline as p
from schemas import Slide,Claim
from planning import presentation_with_plan
from test_planning import seed,FakeAI
from schemas import Review


def test_legacy_slide_schema_remains_readable_and_explicit_layout_is_supported():
    old=Slide(title='Temuan',bullets=[Claim(text='Temuan sumber',fact_ids=['F0001'])],notes='')
    assert old.layout=='auto'
    assert old.model_copy(update={'layout':'risk'}).model_dump()['layout']=='risk'


def test_timeline_and_tables_use_every_task_and_keep_identical_week_values(tmp_path):
    from planning import build_plan
    plan,facts=seed(tmp_path)
    build_plan(tmp_path,lambda **kw:None,FakeAI([plan,Review(passed=True,issues=[])]))
    merged=json.loads(presentation_with_plan(tmp_path).read_text(encoding='utf-8'))
    for layout in ['timeline','action_table']:
        tasks=[t for s in merged['slides'] if s.get('layout')==layout for t in s['tasks']]
        assert len(tasks)==len(plan.tasks)
        assert {t['id']:(t['start_week'],t['duration_weeks'],t['depends_on']) for t in tasks}=={
            t.id:(t.start_week,t.duration_weeks,t.depends_on) for t in plan.tasks}
    assert all(s['proposal'] for s in merged['slides'] if s.get('tasks'))


def test_local_renderer_varies_layouts_and_never_drops_long_text(tmp_path,monkeypatch):
    monkeypatch.setattr(p,'AI',lambda *a:(_ for _ in ()).throw(AssertionError('No API allowed')))
    long=' '.join('Kata'+str(n) for n in range(230))
    report={'title':'Contoh','uncertainties':[],'slides':[
        {'title':'Pembuka','layout':'cover','notes':'','bullets':[{'text':'Materi rekaan.','fact_ids':['F1']}]},
        {'title':'Ringkasan utama','layout':'overview','notes':'','bullets':[{'text':'Data dasar perlu dikonfirmasi.','fact_ids':['F1']},{'text':'Kapasitas belum diketahui.','fact_ids':['F1']}]},
        {'title':'Temuan panjang','layout':'findings','notes':'','bullets':[{'text':long,'fact_ids':['F1']}]}]}
    p.write_json(tmp_path/'report.json',report)
    p.render_pptx(tmp_path)
    design=json.loads((tmp_path/'presentation-layout.json').read_text())
    # Public edition uses the portable neutral layout engine (v4).
    assert design['version']==4 and design['paid_calls']==0
    assert {'cover','overview','findings'}<={s['layout'] for s in design['slides']}
    assert design['slide_count']>3
    with zipfile.ZipFile(tmp_path/'presentation.pptx') as z:
        text=' '.join(' '.join(ET.fromstring(z.read(n)).itertext()) for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
        for token in long.split():assert token in text
    assert all(g['x']+g['w']<=13.36 and g['y']+g['h']<=7.52 for g in design['geometry'])


def test_all_plan_tasks_are_visible_in_editable_tables_and_source_stays_unchanged(tmp_path):
    from planning import build_plan
    plan,facts=seed(tmp_path)
    source=(tmp_path/'report.json').read_bytes()
    build_plan(tmp_path,lambda **kw:None,FakeAI([plan,Review(passed=True,issues=[])]))
    p.render_pptx(tmp_path)
    assert (tmp_path/'report.json').read_bytes()==source
    ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    with zipfile.ZipFile(tmp_path/'presentation.pptx') as z:
        tables=[]
        for n in z.namelist():
            if n.startswith('ppt/slides/slide') and n.endswith('.xml'):
                tables.extend(ET.fromstring(z.read(n)).findall('.//a:tbl',ns))
        text=' '.join(' '.join(t.itertext()) for t in tables)
        assert len(tables)>=1
        for task in plan.tasks:assert task.id in text


def test_long_task_deliverable_is_kept_in_notes_and_excel_input(tmp_path):
    from planning import build_plan
    plan,facts=seed(tmp_path)
    full='Dokumen keluaran terperinci dengan definisi elemen data dan kriteria penerimaan. '*3
    plan.tasks[0].deliverable=full.strip()
    build_plan(tmp_path,lambda **kw:None,FakeAI([plan,Review(passed=True,issues=[])]))
    p.render_pptx(tmp_path)
    assert json.loads((tmp_path/'plan.json').read_text(encoding='utf-8'))['tasks'][0]['deliverable']==full.strip()
    with zipfile.ZipFile(tmp_path/'presentation.pptx') as z:
        notes=' '.join(' '.join(ET.fromstring(z.read(n)).itertext()) for n in z.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml'))
        assert full.strip() in notes
