from audio_speakers import align_speakers

def test_alignment_preserves_primary_words_and_punctuation():
 text='Quarter dua tahun lalu. Ya, betul.'
 voice=[{'text':'Konter dua tahun lalu.','speaker':'A','start':0,'end':3},{'text':'Ya betul','speaker':'B','start':3,'end':5}]
 records,audit=align_speakers(text,voice)
 assert ' '.join(r['text'] for r in records)==text
 assert records[0]['speaker']=='Pembicara 1' and records[-1]['speaker']=='Pembicara 2'
 assert audit['word_sequence_preserved'] and not audit['accuracy_measured']
 assert audit['differences_not_ground_truth']

def test_ambiguous_insert_between_voices_never_guesses():
 records,audit=align_speakers('Awal. Kata tambahan panjang di antara dua ucapan. Akhir.',[{'text':'Awal.','speaker':'A','start':0,'end':1},{'text':'Akhir.','speaker':'B','start':3,'end':4}])
 assert any(r['speaker']=='Pembicara belum dipastikan' for r in records)
 assert audit['speaker_unknown_words']>0

def test_labels_not_guessed_from_person_mentioned_in_text():
 records,_=align_speakers('Pak Ali belum setuju.',[{'text':'Pak Ali belum setuju.','speaker':'A','start':0,'end':2}])
 assert records[0]['speaker']=='Pembicara 1'

def test_budget_precheck_never_calls_provider(tmp_path,monkeypatch):
 import audio_speakers as a
 import pytest
 source=tmp_path/'source.mp3';source.write_bytes(b'fixture')
 def compress(src,target):target.write_bytes(b'fixture upload');return 2968
 monkeypatch.setattr(a,'compress_audio',compress)
 monkeypatch.setenv('MAX_TRANSCRIPTION_USD_PER_JOB','0')
 with pytest.raises(ValueError,match='batas biaya'):a.transcribe_with_speakers(source,tmp_path,lambda **kw:None,client=object())
