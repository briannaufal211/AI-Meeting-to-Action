"""Portable offline XLSX export. No AI requests or private desktop runtime required."""
from pathlib import Path
import json,sys
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.worksheet.table import Table,TableStyleInfo
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter as col
from openpyxl.workbook.properties import CalcProperties

def read(folder,name,default=None):
 p=folder/name
 return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default
def safe(value):
 if isinstance(value,str) and value.startswith(('=','+','-','@')):return "'"+value
 return value
def export(folder,target):
 folder=Path(folder);plan=read(folder,'plan.json');facts=read(folder,'facts.json',[])
 report=read(folder,'report.json',{});audit=read(folder,'plan-review.json',read(folder,'editorial-review.json',{}))
 source=read(folder,'review.json',{});checked=audit.get('passed',False) and source.get('passed',False)
 editorial='editorial' in str(audit.get('method','')) or 'editorial' in str(source.get('method',''))
 label=('Ditinjau editorial' if editorial else 'Lolos audit otomatis') if checked else 'DRAF — masih memerlukan pemeriksaan'
 wb=Workbook();wb.remove(wb.active);wb.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True)
 sheets={n:wb.create_sheet(n) for n in ['Ringkasan','Rekomendasi','Action Plan','Timeline','Asumsi']}
 navy='0F3B4C';teal='1B7F8C';yellow='FFF2CC'
 def base(ws,title,ncols):
  ws.sheet_view.showGridLines=False;ws.sheet_properties.tabColor=teal
  ws.cell(1,1,safe(title));ws.cell(2,1,'USULAN — memerlukan persetujuan dan konfirmasi kapasitas.')
  for row in ws.iter_rows(min_row=1,max_row=1,max_col=ncols):
   for c in row:c.fill=PatternFill('solid',fgColor=navy);c.font=Font(name='Calibri',size=14,color='FFFFFF',bold=True)
  ws.row_dimensions[1].height=32;ws.freeze_panes='C8'
 def grid(ws,headers,rows,widths,name):
  for i,h in enumerate(headers,1):ws.cell(7,i,h)
  for r,values in enumerate(rows,8):
   for c,v in enumerate(values,1):ws.cell(r,c,safe(v))
  for row in ws.iter_rows(min_row=7,max_row=max(8,7+len(rows)),max_col=len(headers)):
   for c in row:
    c.font=Font(name='Calibri',size=10,color='FFFFFF' if c.row==7 else '20313B',bold=c.row==7)
    c.alignment=Alignment(vertical='top',wrap_text=True)
    if c.row==7:c.fill=PatternFill('solid',fgColor=navy)
    elif c.row%2:c.fill=PatternFill('solid',fgColor='F1F6F8')
  for i,w in enumerate(widths,1):ws.column_dimensions[col(i)].width=w
  ws.row_dimensions[7].height=35
  for r,values in enumerate(rows,8):ws.row_dimensions[r].height=min(300,max(55,max(len(str(v or ''))//max(8,int(widths[i]))+1 for i,v in enumerate(values))*15))
  if rows:
   t=Table(displayName=name,ref=f'A7:{col(len(headers))}{7+len(rows)}');t.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True);ws.add_table(t)
 overview,rec,actions,timeline,setup=[sheets[n] for n in sheets]
 tasks=plan.get('tasks',[]);last=7+len(tasks)
 for ws,title,n in [(overview,plan['title'],2),(rec,'Rekomendasi Perbaikan',9),(actions,'Action Plan',26),(timeline,'Timeline Usulan Mingguan',57),(setup,'Asumsi dan Sumber Diskusi',4)]:base(ws,title,n)
 overview['A4']='Jumlah langkah usulan';overview['B4']=f"=COUNTA('Action Plan'!A8:A{last})";overview['A5']='Status rencana';overview['B5']=label
 overview_rows=[]
 for key,title in [('summary','Ringkasan eksekutif'),('outcomes','Hasil sumber'),('conclusions','Kesimpulan sumber')]:
  for claim in report.get(key,[]):overview_rows.append([title,claim.get('text','') if isinstance(claim,dict) else str(claim)])
 for r in plan.get('recommendations',[]):overview_rows.append(['Rekomendasi '+r['priority'],r['title']+'\n'+r['proposal']])
 for a in plan.get('approvals_required',[]):overview_rows.append(['Persetujuan diperlukan',a])
 grid(overview,['Bagian','Informasi dan usulan'],overview_rows,[30,115],'RingkasanTable')
 rec_rows=[[r.get(k,'') for k in ['id','priority','title','problem','proposal','benefit','rationale','tradeoff']]+[', '.join(r.get('fact_ids',[]))] for r in plan.get('recommendations',[])]
 grid(rec,['ID','Prioritas','Rekomendasi','Masalah sumber','Usulan solusi','Manfaat yang diharapkan','Alasan prioritas','Tradeoff','Dasar fakta'],rec_rows,[14,12,34,42,52,38,40,40,18],'RekomendasiTable')
 headers=['ID','Rekomendasi','Fase','Prioritas','Langkah kerja','Keluaran','Kriteria penerimaan','PIC usulan peran','PIC aktual','Mulai minggu','Durasi minggu','Akhir minggu','Tanggal mulai','Tanggal akhir','Estimasi effort person day','Effort per minggu','Prasyarat ID','Sumber daya','Risiko','Mitigasi','KPI usulan','Asumsi tugas','Dasar fakta','Status aktual','Progres aktual','Urutan jadwal']
 rows=[]
 for t in tasks:rows.append([t.get(k,'') for k in ['id','recommendation_id','phase','priority','task','deliverable','acceptance','owner_role']]+[None,t.get('start_week'),t.get('duration_weeks'),None,None,None,t.get('effort_person_days'),None,', '.join(t.get('depends_on',[])),t.get('resources',''),t.get('risk',''),t.get('mitigation',''),t.get('kpi',''),t.get('assumptions',''),', '.join(t.get('fact_ids',[])),'Belum dikonfirmasi',None,None])
 grid(actions,headers,rows,[12,14,22,12,48,43,43,30,25,14,14,14,19,19,20,18,22,35,38,38,40,45,18,25,16,28],'ActionPlanTable')
 actions['A4']='Sel kuning: PIC aktual, minggu mulai, durasi, effort, status dan progres.'
 actions['A5']='Kosong berarti belum ditetapkan. Periksa prasyarat dan kapasitas sebelum menyetujui jadwal.'
 for r,t in enumerate(tasks,8):
  actions[f'L{r}']=f'=IF(AND(ISNUMBER(J{r}),ISNUMBER(K{r}),J{r}>=1,K{r}>=1),J{r}+K{r}-1,"Periksa jadwal")'
  actions[f'M{r}']=f'=IF(Asumsi!$B$3="","",IF(AND(ISNUMBER(J{r}),J{r}>=1),Asumsi!$B$3+7*(J{r}-1),"Periksa minggu"))'
  actions[f'N{r}']=f'=IF(Asumsi!$B$3="","",IF(ISNUMBER(L{r}),Asumsi!$B$3+7*L{r}-1,"Periksa jadwal"))'
  actions[f'P{r}']=f'=IF(OR(O{r}="",K{r}=""),"",IF(AND(ISNUMBER(O{r}),ISNUMBER(K{r}),O{r}>0,K{r}>0),O{r}/K{r},"Periksa effort"))'
  deps=[f'INDEX($L$8:$L${last},MATCH("{d}",$A$8:$A${last},0))' for d in t.get('depends_on',[])]
  prior='MAX('+','.join(deps)+')' if deps else '0'
  actions[f'Z{r}']=f'=IF(OR(NOT(ISNUMBER(J{r})),NOT(ISNUMBER(K{r})),J{r}<1,K{r}<1,L{r}>52),"Periksa jadwal",IF(J{r}<{prior}+1,"Urutan perlu diperbaiki","Sesuai urutan usulan"))'
  for c in ['I','J','K','O','X','Y']:actions[f'{c}{r}'].fill=PatternFill('solid',fgColor=yellow)
  for c in ['M','N']:actions[f'{c}{r}'].number_format='dd mmm yyyy'
  actions[f'Y{r}'].number_format='0%'
 for typ,formula,range_ in [('list','"Belum dikonfirmasi,Belum dimulai,Berjalan,Tertunda,Selesai"',f'X8:X{last}'),('whole','1',f'J8:K{last}'),('decimal','0',f'Y8:Y{last}')]:
  dv=DataValidation(type=typ,formula1=formula,formula2='52' if typ=='whole' else '1' if typ=='decimal' else None,allow_blank=True);dv.showErrorMessage=True
  if typ!='list':dv.operator='between'
  actions.add_data_validation(dv);dv.add(range_)
 actions.conditional_formatting.add(f'Z8:Z{last}',FormulaRule(formula=['ISNUMBER(SEARCH("Periksa",Z8))'],fill=PatternFill('solid',fgColor='FCE4D6')))
 setup['A3']='Tanggal mulai disetujui';setup['A4']='Kapasitas person day per minggu';setup['A5']='Status pemeriksaan';setup['B5']=label
 setup['A6']='Dasar jadwal';setup['B6']='Minggu relatif sejak persetujuan'
 for r in [3,4]:setup[f'B{r}'].fill=PatternFill('solid',fgColor=yellow)
 setup['B3'].number_format='dd mmm yyyy';setup.column_dimensions['A'].width=40;setup.column_dimensions['B'].width=95
 source_rows=[['Asumsi kapasitas',plan.get('capacity_assumption',''),'','']]+[['Asumsi',a,'',''] for a in plan.get('assumptions',[])]+[[f['id'],f.get('quote',''),', '.join(f.get('source_ids',[])),''] for f in facts]
 grid(setup,['Jenis / ID','Asumsi atau kutipan','Sumber','Catatan'],source_rows,[30,110,30,30],'AsumsiTable')
 time_rows=[[t['id'],t.get('task',''),t.get('owner_role',''),None,None]+[None]*52 for t in tasks]
 grid(timeline,['ID','Tugas','PIC usulan','Mulai minggu','Akhir minggu']+['M'+str(i) for i in range(1,53)],time_rows,[12,48,32,14,14]+[6]*52,'TimelineTable')
 for r in range(8,last+1):
  timeline[f'D{r}']=f"=IF('Action Plan'!J{r}=\"\",\"\",'Action Plan'!J{r})";timeline[f'E{r}']=f"='Action Plan'!L{r}"
  for week in range(1,53):timeline.cell(r,week+5,f'=IF(AND(ISNUMBER($D{r}),ISNUMBER($E{r})),IF(AND({week}>=$D{r},{week}<=$E{r}),"●",""),"")')
 target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);wb.save(target)
if __name__=='__main__':export(*sys.argv[1:3])
