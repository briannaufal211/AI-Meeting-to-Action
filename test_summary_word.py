import json,zipfile
import xml.etree.ElementTree as ET
import pytest
from docx import Document
import pipeline
import app
from schemas import Claim,Action,Report,Slide,Review
from summary_word import render_summary_docx


def report():
    return Report(title='Ringkasan Rapat Inventaris',
        summary=[Claim(text='Tim membahas uji coba inventaris.',fact_ids=['F0001'])],
        decisions=[Claim(text='Uji coba dilakukan di satu cabang.',fact_ids=['F0001'])],
        actions=[Action(task='Menghubungi kembali untuk membahas jadwal.',owner='Tidak disebutkan',due='Tentatif Senin, belum disepakati.',fact_ids=['F0001'])],
        uncertainties=['Nama cabang dan tanggal mulai belum ditentukan.'],
        slides=[Slide(title='Uji coba',bullets=[Claim(text='Uji coba satu cabang.',fact_ids=['F0001'])],notes='Usulan jadwal belum final.')])


def test_word_is_editable_native_document_and_preserves_verdict(tmp_path):
    facts=[{'id':'F0001','quote':'Uji coba satu cabang dulu.','source_ids':['S00001']}]
    target=render_summary_docx(tmp_path,report(),facts,Review(passed=False,issues=['Periksa nama cabang di S00001.']))
    doc=Document(target)
    assert doc.paragraphs[0].style.name=='Title'
    text='\n'.join(p.text for p in doc.paragraphs)
    assert 'DRAF - pemeriksaan belum lolos' in text
    assert 'Periksa nama cabang di S00001.' in text
    assert 'F0001 - S00001' in text and 'Uji coba satu cabang dulu.' in text
    action=next(t for t in doc.tables if t.cell(0,1).text=='Tindak lanjut')
    assert action.cell(1,3).text=='Tentatif Senin, belum disepakati.'
    assert '## ' not in text and '**' not in text
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        root=ET.fromstring(z.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        assert root.find('.//w:tblHeader',ns) is not None
        # The neutral public template has section rules and page numbering.
        assert root.find('.//w:pBdr',ns) is not None
        footer=ET.fromstring(z.read('word/footer1.xml'))
        assert footer.find('.//w:fldSimple',ns).attrib['{'+ns['w']+'}instr']=='PAGE'


def test_saved_report_conversion_never_enters_ai_or_modifies_evidence(tmp_path,monkeypatch):
    for name,value in [('report.json',report().model_dump()),('review.json',{'passed':False,'issues':['Belum pasti.']}),('facts.json',[{'id':'F0001','quote':'Uji coba satu cabang dulu.','source_ids':['S00001']}])]:pipeline.write_json(tmp_path/name,value)
    before={name:(tmp_path/name).read_bytes() for name in ['report.json','review.json','facts.json']}
    monkeypatch.setattr(pipeline,'AI',lambda *a:pytest.fail('No AI allowed'))
    monkeypatch.setattr(pipeline,'transcribe',lambda *a:pytest.fail('No transcription allowed'))
    target=pipeline.export_saved_word_summary(tmp_path)
    original=target.read_bytes()
    assert pipeline.export_saved_word_summary(tmp_path)==target and target.read_bytes()==original
    assert before=={name:(tmp_path/name).read_bytes() for name in before}


def test_word_preflight_failure_prevents_paid_calls(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-only')
    monkeypatch.setattr(pipeline,'render_pptx',lambda *a:None)
    monkeypatch.setattr(pipeline.AI,'ask',lambda *a,**kw:pytest.fail('No AI allowed'))
    def unavailable(*a,**kw):raise RuntimeError('Word belum terpasang')
    monkeypatch.setattr(pipeline,'render_summary_docx',unavailable)
    with pytest.raises(RuntimeError,match='Word belum'):pipeline.summarize({'segments':[{'id':'S1','text':'Tes'}]},tmp_path,0,'Tes',lambda **kw:None)


def test_public_files_and_bundle_offer_word_not_markdown(tmp_path,monkeypatch):
    from uuid import uuid4
    jobid=str(uuid4());target=tmp_path/jobid;target.mkdir()
    pipeline.write_json(target/'job.json',{'id':jobid,'status':'completed'})
    render_summary_docx(target,report(),[],Review(passed=True,issues=[]))
    (target/'summary.md').write_text('# Old internal source',encoding='utf-8')
    monkeypatch.setattr(app,'DATA',tmp_path)
    assert 'summary.docx' in app.public_job(target)['files']
    assert 'summary.md' not in app.public_job(target)['files']
    response=app.download(jobid,'summary.docx')
    assert response.media_type=='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    import io
    with zipfile.ZipFile(io.BytesIO(app.bundle(jobid).body)) as z:
        assert 'summary.docx' in z.namelist() and 'summary.md' not in z.namelist()
