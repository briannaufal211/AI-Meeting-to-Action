"""Offline checks for the public portable workbook and synthetic example."""
import json,shutil
from pathlib import Path
from openpyxl import load_workbook
from excel_export import export

def test_saved_example_preserves_unknown_schedule_and_editorial_status(tmp_path):
    source=Path(__file__).parent/'examples/meeting-demo'
    for p in source.glob('*.json'):shutil.copyfile(p,tmp_path/p.name)
    target=tmp_path/'result.xlsx';export(tmp_path,target)
    wb=load_workbook(target)
    assert wb.sheetnames==['Ringkasan','Rekomendasi','Action Plan','Timeline','Asumsi']
    assert wb['Asumsi']['B3'].value is None and wb['Asumsi']['B4'].value is None
    assert wb['Asumsi']['B5'].value=='Ditinjau editorial'
    tasks=json.loads((tmp_path/'plan.json').read_text(encoding='utf-8'))['tasks']
    for row,task in enumerate(tasks,8):
        assert wb['Action Plan'].cell(row,1).value==task['id']
        for key,col in [('start_week',10),('duration_weeks',11),('effort_person_days',15)]:
            assert wb['Action Plan'].cell(row,col).value==task.get(key)
        assert wb['Action Plan'].cell(row,12).data_type=='f'
        assert wb['Action Plan'].cell(row,9).value is None

def test_spreadsheet_untrusted_title_is_literal(tmp_path):
    source=Path(__file__).parent/'examples/meeting-demo'
    for p in source.glob('*.json'):shutil.copyfile(p,tmp_path/p.name)
    plan=json.loads((tmp_path/'plan.json').read_text(encoding='utf-8'))
    plan['tasks'][0]['task']='=HYPERLINK("https://example.invalid","unsafe")'
    (tmp_path/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
    target=tmp_path/'safe.xlsx';export(tmp_path,target)
    cell=load_workbook(target)['Action Plan']['E8']
    assert cell.data_type=='s' and cell.value.startswith("'=")
