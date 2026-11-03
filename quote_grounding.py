"""Repair incomplete adjacent source references only when the literal quote proves them."""
import re

def _tokens(text):
 return [(m.group().casefold(),m.start(),m.end()) for m in re.finditer(r'\w+(?:[.,]\d+)*|[%$]',text)]

def restore_literal_quote(quote,source):
 """Restore a unique literal span, never invent, substitute or remove a quoted word.

 Explicit ellipses may omit source passages. Within a fragment, at most one
 source 'yang' may have been omitted. Numbers and negation are never skipped.
 Punctuation/case differences are resolved by returning actual source characters.
 """
 fragments=[_tokens(x) for x in re.split(r'\.{3,}|…+',quote)]
 fragments=[[t[0] for t in f] for f in fragments if f]
 source_tokens=_tokens(source)
 if not fragments or sum(map(len,fragments))<6:return None
 matches=[]
 for fragment in fragments:
  found=[]
  for start,t in enumerate(source_tokens):
   if t[0]!=fragment[0]:continue
   i=start;j=0;omissions=0
   while i<len(source_tokens) and j<len(fragment):
    if source_tokens[i][0]==fragment[j]:i+=1;j+=1
    elif source_tokens[i][0]=='yang' and omissions<1:omissions+=1;i+=1
    else:break
   if j==len(fragment):found.append((start,i,omissions))
  if not found or len(found)>64:return None
  matches.append(found)
 candidates=[]
 for start,end,omissions in matches[0]:
  cursor=end;skips=omissions
  for found in matches[1:]:
   following=[m for m in found if m[0]>=cursor]
   if not following:break
   match=min(following,key=lambda m:(m[1],m[0]));cursor=match[1];skips+=match[2]
  else:
   if skips<=1:candidates.append((start,cursor))
 if not candidates:return None
 minimum=min(b-a for a,b in candidates);best=set((a,b) for a,b in candidates if b-a==minimum)
 if len(best)!=1:return None
 a,b=best.pop();literal=source[source_tokens[a][1]:source_tokens[b-1][2]]
 if len(literal)>4000:return None
 return literal

def norm(text):return re.sub(r'\s+',' ',text).strip().casefold()

def complete_references(extraction,segments):
 positions={s['id']:i for i,s in enumerate(segments)};changes=[]
 for index,fact in enumerate(extraction.facts):
  if not fact.source_ids or any(s not in positions for s in fact.source_ids):continue
  original=list(fact.source_ids)
  if norm(fact.quote) in norm(' '.join(segments[positions[s]]['text'] for s in original)):continue
  lo=min(positions[s] for s in original);hi=max(positions[s] for s in original)
  candidates=[]
  for start in range(max(0,lo-2),lo+1):
   for stop in range(hi+1,min(len(segments),hi+3)+1):
    window=segments[start:stop];ids=[s['id'] for s in window]
    if set(original).issubset(ids) and norm(fact.quote) in norm(' '.join(s['text'] for s in window)):candidates.append(ids)
  if not candidates:
   cited=' '.join(segments[positions[s]]['text'] for s in original)
   literal=restore_literal_quote(fact.quote,cited)
   if literal is not None:
    previous=fact.quote;fact.quote=literal
    changes.append({'fact_index':index,'original_source_ids':original,'completed_source_ids':original,
      'original_quote':previous,'restored_quote':literal,'method':'unique_literal_source_span',
      'fact_text_unchanged':True,'contains_unconfirmed_speaker':any(segments[positions[s]].get('speaker')=='Pembicara belum dipastikan' for s in original)})
   continue
  size=min(map(len,candidates));minimal=[ids for ids in candidates if len(ids)==size]
  if len(minimal)!=1:continue
  fact.source_ids=minimal[0]
  changes.append({'fact_index':index,'original_source_ids':original,'completed_source_ids':list(fact.source_ids),'quote_unchanged':fact.quote,'method':'unique_minimal_adjacent_literal_match','contains_unconfirmed_speaker':any(s.get('speaker')=='Pembicara belum dipastikan' for s in segments if s['id'] in fact.source_ids)})
 return extraction,changes
