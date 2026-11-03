"""Preserve explicit speaker labels from user-supplied TXT; never infer voice identity."""
import re

def speaker_segments(raw):
    # Covers Speaker 1/Pembicara 1, with optional leading timestamp.
    marker=re.compile(r'^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?(?P<label>(?:Speaker|Pembicara)\s+\d+)\s*(?::\s*(?P<text>.*)|$)',re.I)
    groups=[];label=None;lines=[];seen=False
    def flush():
        if lines:groups.append({'text':'\n'.join(lines),'speaker':label} if label else {'text':'\n'.join(lines)})
    for line in raw.splitlines():
        match=marker.match(line)
        if match:
            flush();lines=[];label=match['label'];seen=True
            if match['text']:lines.append(match['text'])
        elif line.strip():lines.append(line)
    flush()
    if not seen:return None
    result=[]
    for group in groups:
        for start in range(0,len(group['text']),1200):result.append({**group,'text':group['text'][start:start+1200],'id':f'S{len(result)+1:05}'})
    return result
