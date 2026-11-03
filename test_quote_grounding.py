import pytest
from schemas import Extraction,Fact
from quote_grounding import complete_references
from pipeline import validate_facts
from quote_grounding import restore_literal_quote

@pytest.mark.parametrize('quote,source',[
 ('kalau memang kita harus suspend mereka sampai ke orangnya ... berarti kita perlu cari yang baru.', 'Nah, kalau memang kita harus suspend mereka sampai ke orangnya dan segala macam, suspend, tapi kan berarti kita perlu cari yang baru. Nah.'),
 ('kalau bagus tapi kita ngerasa belum saatnya, ya kita mungkin belum akan apply', 'Kalau yang bagus tapi kita ngerasa belum saatnya, ya kita mungkin belum akan apply, gitu ya.'),
 ('kalau lu telat ... ada penalty misalnya. ... bayarannya tunggu bulan depan lagi, 30 hari cycle lagi.', 'kalau lu telat, kalau lu apa segala macam, ada penalty misalnya. Contoh, Enggak, bayarannya tunggu bulan depan lagi, 30 hari cycle lagi.'),
])
def test_documented_omissions_restore_actual_source_not_a_new_model_request(quote,source):
 original='Usulan, bukan keputusan.'
 ex=Extraction(facts=[Fact(text=original,quote=quote,source_ids=['S1'])])
 restored,changes=complete_references(ex,[{'id':'S1','text':source}])
 validate_facts(restored.facts,[{'id':'S1','text':source}])
 assert changes[0]['method']=='unique_literal_source_span' and restored.facts[0].quote in source
 assert restored.facts[0].text==original

@pytest.mark.parametrize('quote,source',[
 ('Anggaran disetujui sebesar Rp800.000 untuk proyek ini','Anggaran disetujui sebesar Rp900.000 untuk proyek ini'),
 ('Tim belum menyetujui rencana pelaksanaan pada Senin','Tim menyetujui rencana pelaksanaan pada Senin'),
 ('Tim menyetujui rencana pelaksanaan pada Senin','Tim tidak menyetujui rencana pelaksanaan pada Senin'),
 ('kami menerima usulan perubahan ini besok ... akan dijalankan','kami menerima usulan perubahan ini besok dan akan dijalankan. kami menerima usulan perubahan ini besok dan akan dijalankan.'),
])
def test_restore_does_not_guess_amounts_negation_or_duplicate_spans(quote,source):
 assert restore_literal_quote(quote,source) is None

def test_negation_from_previous_segment_is_literally_grounded():
 segments=[{'id':'S1','text':'Nggak','speaker':'Pembicara belum dipastikan'},{'id':'S2','text':'pernah lagi.'}]
 result,changes=complete_references(Extraction(facts=[Fact(text='Tidak pernah lagi.',quote='Nggak pernah lagi.',source_ids=['S2'])]),segments)
 assert result.facts[0].source_ids==['S1','S2'] and changes[0]['contains_unconfirmed_speaker']
 validate_facts(result.facts,segments)

def test_negation_that_is_not_present_is_never_invented():
 segments=[{'id':'S1','text':'pernah lagi.'}]
 result,changes=complete_references(Extraction(facts=[Fact(text='Tidak.',quote='Nggak pernah lagi.',source_ids=['S1'])]),segments)
 assert not changes
 with pytest.raises(ValueError):validate_facts(result.facts,segments)

def test_ambiguous_reference_completion_is_not_guessed():
 segments=[{'id':'S1','text':'iya'},{'id':'S2','text':'iya'},{'id':'S3','text':'iya'}]
 result,changes=complete_references(Extraction(facts=[Fact(text='Iya.',quote='iya iya',source_ids=['S2'])]),segments)
 assert not changes
 with pytest.raises(ValueError):validate_facts(result.facts,segments)

def test_valid_reference_is_not_changed():
 e=Extraction(facts=[Fact(text='Iya.',quote='Iya.',source_ids=['S1'])])
 result,changes=complete_references(e,[{'id':'S1','text':'Iya.'}]);assert not changes and result.facts[0].source_ids==['S1']
