"""Offline regression tests for evidence correction, informative coverage and paid cache reuse."""
from copy import deepcopy
import json
import pytest
import pipeline as p
from schemas import Claim, Action, Report, Review, QualityRepair, FactCorrection
from summary_quality import apply_evidence_repair, SUMMARY_STANDARD
from test_quality import Model


def material():
    segments = [
        {'id': 'S00001', 'text': 'Kita punya mapping nama vendor dan jenis pekerjaannya, itu ada ya?'},
        {'id': 'S00002', 'text': 'Saya minta Pak Dodi mencari dan mengkurasi vendor di database.'},
        {'id': 'S00003', 'text': 'Kalau kurang cari lagi di luar. Pak Ferry kalau ada rekomendasi bisa dibantu.'},
    ]
    facts = [{'id': 'F0001', 'text': 'Diminta membuat mapping.', 'quote': 'itu ada ya?', 'source_ids': ['S00001']}]
    base = Report(title='Vendor', summary=[Claim(text='Diminta membuat mapping.',fact_ids=['F0001'])], decisions=[],actions=[],uncertainties=[],slides=[])
    corrected = base.model_copy(deep=True)
    corrected.summary[0].text = 'Peserta bertanya apakah mapping sudah tersedia.'
    corrected.actions = [Action(task='Penugasan mencari dan mengkurasi vendor.', owner='Pak Dodi',due='Tidak disebutkan',fact_ids=['F0002'])]
    bundle = QualityRepair(report=corrected,
        fact_updates=[FactCorrection(id='F0001',text=corrected.summary[0].text,quote='itu ada ya?',source_ids=['S00001'])],
        additional_facts=[FactCorrection(id='F0002',text='Pak Dodi diminta mencari dan mengkurasi vendor.',quote='Saya minta Pak Dodi mencari dan mengkurasi vendor di database.',source_ids=['S00002'])])
    return {'segments':segments}, facts, base, bundle


def apply(bundle, facts, t):
    return apply_evidence_repair(bundle, facts, t['segments'],p.validate_facts,p.validate_report,p.validate_slide_count,-1)


def test_fact_and_missing_action_are_repaired_together_and_rereviewed(tmp_path, monkeypatch):
    monkeypatch.setenv('MAX_AI_REVISIONS','1')
    t,f,r,b=material()
    p.write_json(tmp_path/'transcript.json',t)
    p.write_json(tmp_path/'facts.json',f)
    p.write_json(tmp_path/'report.json',r.model_dump())
    model=Model([Review(passed=False,issues=['Pertanyaan berubah menjadi tugas; penugasan Dodi hilang.']),b,Review(passed=True,issues=[])])
    final, verdict=p.check_and_repair(t,tmp_path,r,f,-1,'',lambda **kw:None,model)
    assert verdict.passed and len(model.calls)==3
    assert final.actions[0].owner=='Pak Dodi'
    assert model.calls[-1][2]['facts'][0]['text']=='Peserta bertanya apakah mapping sudah tersedia.'
    assert len(json.loads((tmp_path/'facts.json').read_text()))==2
    assert f[0]['text']!='Diminta membuat mapping.'
    p.check_and_repair(t,tmp_path,r,f,-1,'',lambda **kw:None,model)
    assert len(model.calls)==3
    doc=p.render_summary_docx(tmp_path,final,f,verdict)
    from docx import Document
    assert 'Diminta membuat mapping.' not in '\n'.join(x.text for x in Document(doc).paragraphs)


@pytest.mark.parametrize('bad', ['quote','source','id','duplicate','report','slides'])
def test_invalid_repairs_are_rejected_without_mutating_original(bad):
    t,f,r,b=material(); before=deepcopy(f)
    if bad=='quote':b.fact_updates[0].quote='buat mapping sekarang'
    if bad=='source':b.fact_updates[0].source_ids=['S99999']
    if bad=='id':b.additional_facts[0].id='F0009'
    if bad=='duplicate':b.fact_updates.append(b.fact_updates[0])
    if bad=='report':b.report.actions[0].fact_ids=['F9999']
    if bad=='slides':
        from schemas import Slide
        b.report.slides=[Slide(title='Tidak diminta',bullets=[Claim(text='T',fact_ids=['F0001'])],notes='')]
    with pytest.raises(ValueError): apply(b,f,t)
    assert f==before


def test_invalid_cached_repair_never_causes_another_paid_request(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_AI_REVISIONS','1')
    t,f,r,b=material();b.fact_updates[0].quote='Kutipan rekaan'
    p.write_json(tmp_path/'facts.json',f)
    m=Model([Review(passed=False,issues=['Perbaiki.']),b])
    for _ in range(2):
        with pytest.raises(ValueError):p.check_and_repair(t,tmp_path,r,f,-1,'',lambda **kw:None,m)
    assert len(m.calls)==2 and (tmp_path/'quality-repair-v3.json').exists()


def test_resume_between_repair_and_audit_reuses_bundle(tmp_path,monkeypatch):
    monkeypatch.setenv('MAX_AI_REVISIONS','1')
    t,f,r,b=material()
    p.write_json(tmp_path/'facts.json',f)
    p.write_json(tmp_path/'quality-repair-v3.json',b.model_dump())
    p.write_json(tmp_path/'review-initial.json',{'passed':False,'issues':['Perbaiki.']})
    model=Model([Review(passed=True,issues=[])])
    _,review=p.check_and_repair(t,tmp_path,r,f,-1,'',lambda **kw:None,model)
    assert review.passed and len(model.calls)==1
    assert model.calls[0][0] is Review


def test_client_summary_standard_requires_context_actions_and_uncertainty():
    for text in ['klien','hasil terukur','actions tidak boleh kosong','Pertanyaan','Tidak disebutkan']:
        assert text in SUMMARY_STANDARD
