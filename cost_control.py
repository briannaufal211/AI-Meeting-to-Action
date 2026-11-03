"""Persistent call ledger; no network operations in this module."""
import hashlib
import json
import os
import time


class CallJournal:
    def __init__(self, output, model, save):
        self.output, self.model, self.save = output, model, save
        self.path = output / 'cost-control.json'
        self.data = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'requests': []}
        self.cache = output / 'ai-cache'
        self.cache.mkdir(exist_ok=True)

    def signature(self, schema, instruction, payload, max_tokens):
        content = {'model': self.model, 'schema': schema.model_json_schema(), 'instruction': instruction,
                   'payload': payload, 'max_tokens': max_tokens}
        return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def get(self, signature, schema):
        path = self.cache / (signature + '.json')
        return schema.model_validate_json(path.read_text(encoding='utf-8')) if path.exists() else None

    def begin(self, signature, schema, max_tokens):
        for request in self.data['requests']:
            if request['signature'] == signature and request['status'] in {'in_flight', 'uncertain', 'invalid'}:
                raise ValueError('Permintaan AI sebelumnya belum pasti atau tidak lengkap. Tidak dikirim ulang untuk menghindari biaya ganda. Periksa OpenAI Usage dan cost-control.json sebelum percobaan baru.')
        maximum = int(os.getenv('MAX_PAID_CALLS_PER_JOB', '12'))
        if len(self.data['requests']) >= maximum:
            raise ValueError('Batas jumlah permintaan API pekerjaan ini tercapai. Tidak ada panggilan baru yang dikirim.')
        record = {'signature': signature, 'schema': schema.__name__, 'model': self.model,
                  'max_output_tokens': max_tokens, 'status': 'in_flight', 'started_at': time.time()}
        self.data['requests'].append(record)
        self.save(self.path, self.data)
        return record

    def finish(self, record, status, response_id=None):
        record.update(status=status, finished_at=time.time())
        if response_id:
            record['response_id'] = response_id
        self.save(self.path, self.data)

    def store(self, signature, parsed):
        self.save(self.cache / (signature + '.json'), parsed.model_dump())
