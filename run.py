import os
import sys
import webbrowser
import threading
import urllib.request
import json
from pathlib import Path
from dotenv import load_dotenv
import uvicorn
root=Path(__file__).resolve().parent
load_dotenv(root/'.env')
if __name__=='__main__':
    port=int(os.getenv('APP_PORT','8765'))
    url=f'http://127.0.0.1:{port}'
    if '--no-browser' not in sys.argv:
        try:
            with urllib.request.urlopen(url+'/api/health',timeout=2) as response:
                health=json.load(response)
            if health.get('ok') and 'whisper_model' in health:
                if health.get('summary_standard_version', 0) < 3 or health.get('summary_docx_supported') is not True or health.get('planning_supported') is not True or health.get('transcription_api_version',0)<1 or health.get('speaker_audio_supported') is not True or health.get('output_modes_supported') is not True:
                    print('Layanan aplikasi versi lama masih berjalan. Membuka Mulai.cmd lagi tidak mengganti proses lama.')
                    print('Setelah semua pekerjaan selesai, tutup layanan aplikasi dengan Ctrl+C lalu jalankan Mulai.cmd dari folder proyek aktif. Layanan n8n tidak perlu dimulai ulang untuk pembaruan ringkasan ini.')
                    print('Muat ulang konfigurasi hanya membaca pengaturan, bukan memuat ulang kode program.')
                    sys.exit(2)
                webbrowser.open(url)
                print('Aplikasi versi terbaru sudah berjalan. Gunakan Muat ulang konfigurasi jika .env baru diubah.')
                sys.exit(0)
        except (OSError,ValueError):
            pass
        threading.Timer(2,lambda:webbrowser.open(url)).start()
    uvicorn.run('app:app',host='127.0.0.1',port=port,workers=1,access_log=False)
