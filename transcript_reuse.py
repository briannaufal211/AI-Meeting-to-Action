"""Reuse complete, configuration-identical audio checkpoints; never copy paid ledgers."""
import json,shutil
from pathlib import Path

def reuse_speaker_transcript(output,signatures,write_json):
    output=Path(output)
    ledger=output/'cost-control.json'
    if ledger.exists() and json.loads(ledger.read_text(encoding='utf-8')).get('requests'):return None
    for candidate in sorted(output.parent.iterdir()):
        if candidate==output or not candidate.is_dir():continue
        if not all((candidate/'ai-cache'/(sig+'.json')).exists() for sig in signatures):continue
        if not all((candidate/n).exists() for n in ['transcript.json','transcript.txt','transcription-alignment.json']):continue
        try:
            alignment=json.loads((candidate/'transcription-alignment.json').read_text(encoding='utf-8'))
            result=json.loads((candidate/'transcript.json').read_text(encoding='utf-8'))
        except (ValueError,OSError):continue
        if alignment.get('word_sequence_preserved') is not True or not result.get('segments'):continue
        for name in ['transcript.txt','transcription-alignment.json','voice-evidence.json','primary-response.json']:
            if (candidate/name).exists():shutil.copy2(candidate/name,output/name)
        result['reused_from_job']=candidate.name;write_json(output/'transcript.json',result)
        write_json(output/'transcription-reuse.json',{'source_job_id':candidate.name,'signature_match':True,'audio_requests_sent':0,'words_unchanged':True})
        return result
    return None
