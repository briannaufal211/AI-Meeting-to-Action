from speaker_import import speaker_segments
import pipeline as p
import json

def test_explicit_speaker_labels_and_continuations():
 r=speaker_segments('Speaker 1: Quarter dua tahun lalu.\nLanjut kalimat.\nSpeaker 2: Baik, Pak.')
 assert [s['speaker'] for s in r]==['Speaker 1','Speaker 2']
 assert r[0]['text']=='Quarter dua tahun lalu.\nLanjut kalimat.'

def test_plain_text_never_gets_guessed_speakers():
 assert speaker_segments('Quarter dua tahun lalu.\nSaya konsultan.') is None

def test_timestamp_and_multiline_labels():
 r=speaker_segments('[00:01:02] Pembicara 1: Uji.\nSpeaker 2\nSetuju.')
 assert r[0]['speaker']=='Pembicara 1' and r[1]['text']=='Setuju.'

def test_long_turn_keeps_same_speaker():
 r=speaker_segments('Speaker 1: '+'kata '*400)
 assert len(r)==2 and all(s['speaker']=='Speaker 1' for s in r)

def test_text_import_preserves_labels_without_any_audio_api(tmp_path,monkeypatch):
 p.write_json(tmp_path/'job.json',{'input_kind':'text'})
 (tmp_path/'input.txt').write_text('Speaker 1: Quarter dua tahun lalu.\nSpeaker 2: Betul.',encoding='utf-8')
 monkeypatch.setattr(p,'transcribe',lambda *args:(_ for _ in ()).throw(AssertionError('Audio API forbidden')))
 t=p.prepare_transcript(tmp_path,lambda **kw:None)
 assert len(t['segments'])==2 and t['speaker_labels_source']=='user_supplied_text'
 assert 'Speaker 2: Betul.' in (tmp_path/'transcript.txt').read_text(encoding='utf-8')
