"""Portable Word report using a neutral, editable public template."""
from pathlib import Path
import json,re
from copy import deepcopy

ROOT=Path(__file__).resolve().parent
def clean(value):return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]','',str(value or ''))
def render_summary_docx(output,report,facts,review):
    from docx import Document
    from docx.shared import Pt,Cm,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.style import WD_STYLE_TYPE
    from lxml import etree
    data=report.model_dump() if hasattr(report,'model_dump') else report
    verdict=review.model_dump() if hasattr(review,'model_dump') else review
    output=Path(output);output.mkdir(exist_ok=True,parents=True)
    doc=Document()
    for section in doc.sections:
        section.page_width=Cm(21);section.page_height=Cm(29.7)
        section.left_margin=Cm(2);section.right_margin=Cm(2)
        section.top_margin=Cm(2);section.bottom_margin=Cm(2)
        footer=section.footer.paragraphs[0];footer.alignment=1
        page=OxmlElement('w:fldSimple');page.set(qn('w:instr'),'PAGE');footer._p.append(page)
    for name,size,color,bold in [('Normal',11,'000000',False),('Title',20,'1F3864',True),('Subtitle',14,'2F5496',False),('Heading 1',15,'1F3864',True),('Heading 2',12,'2F5496',True),('List Bullet',11,'000000',False)]:
        st=doc.styles[name] if name in doc.styles else doc.styles.add_style(name,WD_STYLE_TYPE.PARAGRAPH)
        st.font.name='Calibri';st.font.size=Pt(size);st.font.color.rgb=RGBColor.from_string(color);st.font.bold=bold
        st.paragraph_format.space_after=Pt(3 if name in {'Normal','List Bullet'} else 6)
        st.paragraph_format.line_spacing=1.1
        st.paragraph_format.widow_control=True
        if name.startswith('Heading'):
            st.paragraph_format.space_before=Pt(12 if name=='Heading 1' else 8);st.paragraph_format.keep_with_next=True
    doc.add_paragraph('RINGKASAN PERTEMUAN','Title');doc.add_paragraph(clean(data['title']),'Subtitle')
    used=set()
    def paragraph(text,ids=None,style=None):
        p=doc.add_paragraph(style=style or 'Normal');value=clean(text)
        pattern=r'(?:Rp|US\$)\s?[\d.,]+(?:\s?(?:juta|miliar))?|\d+(?:[.,]\d+)?%|\b\d+\s+(?:vendor|cabang|aset|minggu)\b'
        cursor=0
        for match in re.finditer(pattern,value):
            if match.start()>cursor:p.add_run(value[cursor:match.start()])
            p.add_run(match.group()).bold=True;cursor=match.end()
        if cursor<len(value):p.add_run(value[cursor:])
        if ids:
            used.update(ids)
            r=p.add_run(' ['+', '.join(ids)+']');r.font.size=Pt(8);r.font.color.rgb=RGBColor.from_string('5B6B73')
        return p
    def bullets(items):
        for item in items:paragraph(item['text'],item['fact_ids'],'List Bullet')
    def heading(text,level=1):
        p=doc.add_heading(text,level=level)
        if level==1:
            borders=OxmlElement('w:pBdr');bottom=OxmlElement('w:bottom')
            bottom.set(qn('w:val'),'single');bottom.set(qn('w:sz'),'6');bottom.set(qn('w:color'),'1F3864')
            borders.append(bottom);p._p.get_or_add_pPr().append(borders)
        return p
    section_number=[0]
    def section(text):
        section_number[0]+=1;heading(str(section_number[0])+'. '+text)
    def table(headers,rows,widths,header=True):
        t=doc.add_table(rows=0,cols=len(widths));t.autofit=False
        for col,w in zip(t.columns,widths):col.width=Cm(w)
        for i,values in enumerate(([headers]+rows) if header else rows):
            row=t.add_row();pr=row._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
            if i==0 and header:pr.append(OxmlElement('w:tblHeader'))
            for cell,value,w in zip(row.cells,values,widths):
                cell.width=Cm(w);cell.text=clean(value)
                tcpr=cell._tc.get_or_add_tcPr();shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'1F3864' if i==0 and header else ('EEF3F8' if i%2 else 'FFFFFF'));tcpr.append(shade)
                margin=OxmlElement('w:tcMar')
                for edge in ['top','bottom','left','right']:
                    e=OxmlElement('w:'+edge);e.set(qn('w:w'),'80');e.set(qn('w:type'),'dxa');margin.append(e)
                tcpr.append(margin)
                for p in cell.paragraphs:
                    p.paragraph_format.space_after=Pt(3);p.paragraph_format.keep_with_next=bool(i==0 and header)
                    for run in p.runs:
                        run.font.name='Calibri';run.font.size=Pt(10);run.font.bold=bool(i==0 and header);run.font.color.rgb=RGBColor.from_string('FFFFFF' if i==0 and header else '000000')
        borders=OxmlElement('w:tblBorders')
        for edge in ['top','left','bottom','right','insideH','insideV']:
            e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D3DDE0');borders.append(e)
        t._tbl.tblPr.append(borders);doc.add_paragraph();return t
    if not verdict['passed']:
        paragraph('Status pemeriksaan: DRAF - pemeriksaan belum lolos.').runs[0].bold=True
        heading('Temuan Pemeriksaan')
        for issue in verdict.get('issues',[]):paragraph(issue,style='List Bullet')
    metadata={}
    if (output/'job.json').exists():metadata=json.loads((output/'job.json').read_text(encoding='utf-8'))
    date=data.get('meeting_date');date_text=date['text'] if date else 'Tidak dapat dipastikan dari sumber yang tersedia'
    if date:used.update(date['fact_ids'])
    status_text='CONTOH DATA REKAAN - bukan hasil rekaman klien' if metadata.get('demo') else ('Diperiksa otomatis terhadap transkrip' if verdict['passed'] else 'DRAF - pemeriksaan belum lolos')
    if (verdict.get('method')=='editorial_saved_transcript' or metadata.get('recovery_method')=='editorial_saved_transcript') and verdict['passed']:status_text='Ditinjau editorial terhadap transkrip tersimpan'
    table([], [['Sumber',metadata.get('filename') or 'Transkrip diskusi yang diproses'],['Tanggal pertemuan',date_text],['Status pemeriksaan',status_text]],[4,13],False)
    heading('Ringkasan Eksekutif');bullets(data.get('summary',[]))
    if data.get('context') or data.get('participants'):section('Konteks')
    if data.get('context'):bullets(data['context'])
    if data.get('participants'):
        heading('Pihak dan peran yang disebut',2);bullets(data['participants'])
    section('Informasi Utama');topic_number=section_number[0]
    if data.get('topics'):
        for i,topic in enumerate(data['topics'],1):
            heading(f"{topic_number}.{i} {topic['title']}",2);bullets(topic['points'])
            if topic.get('status'):paragraph('Status: '+topic['status']['text'],topic['status']['fact_ids'])
    else:bullets(data.get('summary',[]))
    if data.get('outcomes'):section('Hasil Pertemuan');bullets(data['outcomes'])
    if data.get('risk_items'):
        section('Risiko');paragraph('Tingkat dan mitigasi yang berlabel Analisis usulan merupakan penilaian AI berdasarkan transkrip, bukan penetapan atau keputusan rapat.').paragraph_format.keep_with_next=True
        rows=[]
        for r in data['risk_items']:
            used.update(r['fact_ids']);rows.append([r['title'],r['description']+'\nDampak: '+r['impact']+'\n['+', '.join(r['fact_ids'])+']',r['level'],r['mitigation']+'\n'+r['assessment_basis']])
        table(['Risiko','Penjelasan dan dampak','Tingkat','Arah mitigasi'],rows,[3,6,2,6])
    section('Keputusan');heading('Keputusan yang disebut atau tindakan yang dilaporkan',2)
    if data.get('decisions'):bullets(data['decisions'])
    else:paragraph('Tidak ada keputusan eksplisit yang teridentifikasi.')
    heading('Hal yang belum diputuskan',2)
    if data.get('open_decisions'):bullets(data['open_decisions'])
    else:paragraph('Tidak ada keputusan terbuka tambahan yang dapat dipastikan dari data terstruktur.')
    if data.get('conclusions'):
        section('Kesimpulan');paragraph('Sintesis berikut merangkum makna pembahasan dan tidak menambah komitmen baru.');bullets(data['conclusions'])
    section('Tindak Lanjut')
    paragraph('Tabel ini memuat tindak lanjut yang didukung sumber. PIC atau tenggat yang tidak pasti tidak diisi dengan tebakan. Rekomendasi dan rencana implementasi tambahan disajikan sebagai usulan dalam PPT dan Excel bila dipilih.').paragraph_format.keep_with_next=True
    if data.get('actions'):
        rows=[]
        for i,a in enumerate(data['actions'],1):
            used.update(a['fact_ids']);rows.append([str(i),a['task']+'\n['+', '.join(a['fact_ids'])+']',a.get('owner') or 'Tidak disebutkan',a.get('due') or 'Tidak disebutkan'])
        table(['No','Tindak lanjut','PIC disebut','Tenggat disebut'],rows,[.8,8.2,4,4])
    else:paragraph('Tidak ada tugas eksplisit yang teridentifikasi.')
    section('Poin yang Perlu Diverifikasi')
    for text in data.get('uncertainties',[]):paragraph(text,style='List Bullet')
    if not data.get('uncertainties'):paragraph('Tidak ada ketidakpastian tambahan yang tercatat; ini bukan jaminan ketepatan semua ucapan.')
    section('Catatan Keterbatasan Data')
    paragraph('Pemeriksaan otomatis tidak menjamin ketepatan setiap ucapan terhadap audio. Identitas pembicara, istilah dan nama yang belum pasti harus diperlakukan sesuai catatan sumber. Penuturan tentang kasus atau dugaan bukan pembuktian formal. Jadwal usulan memerlukan konfirmasi kapasitas dan persetujuan sebelum dijalankan.')
    if facts:
        if len(used)>12 and metadata.get('recovery_method')!='editorial_saved_transcript':doc.add_page_break()
        heading('Rujukan Transkrip')
        paragraph('Kode pada isi laporan menautkan informasi ke kutipan sumber berikut. Berkas transkrip lengkap tetap menjadi acuan konteks.')
        for fact in facts:
            if used and fact['id'] not in used:continue
            paragraph(fact['id']+' - '+', '.join(fact.get('source_ids',[]))).runs[0].bold=True
            paragraph(fact.get('quote',''))
    footer=doc.sections[0].footer.paragraphs[0]
    for child in list(footer._p):
        if child.tag!=qn('w:pPr'):footer._p.remove(child)
    footer.alignment=1
    def foot_text(text):
        run=footer.add_run(text);run.font.name='Calibri';run.font.size=Pt(8);run.font.color.rgb=RGBColor.from_string('777777')
    foot_text('Ringkasan Pertemuan | Halaman ')
    for name,prefix in [('PAGE',''),('NUMPAGES',' dari ')]:
        if prefix:foot_text(prefix)
        field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),name)
        run=OxmlElement('w:r');text=OxmlElement('w:t');text.text='1';run.append(text);field.append(run);footer._p.append(field)
    doc.settings.element.append(OxmlElement('w:updateFields'));doc.settings.element[-1].set(qn('w:val'),'true')
    doc.core_properties.title=clean(data['title']);doc.core_properties.subject='Ringkasan pertemuan berbasis sumber';doc.core_properties.author='Otomasi Diskusi Lokal'
    target=output/'summary.docx';temp=output/'.summary.docx.tmp';doc.save(temp);temp.replace(target);return target
