"""Same-origin cloud hosting with password-protected classroom administration."""
import json
import os
import re
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import qa_server as qa

ADMIN_PASSWORD = os.environ.get('QA_ADMIN_PASSWORD', '')
OPEN_UNTIL = 0.0
ADMIN_FAILURES = []
VERSION = '2026-11-15-cloud-1'

class CloudHandler(qa.Handler):
    def html(self, body):
        encoded=body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(encoded)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Set-Cookie',f'qa_session={qa.TOKEN}; SameSite=Strict; HttpOnly; Secure; Path=/')
        self.end_headers();self.wfile.write(encoded)

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/health':
            self.reply(200,{'version':VERSION,'cloud':True,'provider':qa.PROVIDER,'model':qa.MODEL,
                'key_configured':bool(qa.API_KEY),'classroom_open':time.time()<OPEN_UNTIL and bool(qa.API_KEY),
                'calls':qa.CALLS,'limit':qa.MAX_CALLS,'expires_at':int(OPEN_UNTIL)})
        elif path=='/admin':
            self.html((qa.ROOT/'admin.html').read_text('utf-8').replace('__QA_SESSION_TOKEN__',qa.TOKEN))
        elif path in ('/','/index.html'):
            self.html((qa.ROOT/'index.html').read_text('utf-8').replace('__QA_SESSION_TOKEN__',qa.TOKEN))
        else: self.reply(404,{'error':'找不到此頁'})

    def do_POST(self):
        global OPEN_UNTIL
        path=urlsplit(self.path).path
        origin=self.headers.get('Origin','')
        if origin and urlsplit(origin).netloc!=self.headers.get('Host'):
            self.reply(403,{'error':'僅接受同一網站的操作'});return
        if path in ('/api/config','/api/check','/api/close'):
            now=time.time()
            with qa.LOCK:
                ADMIN_FAILURES[:]=[t for t in ADMIN_FAILURES if now-t<300]
                limited=len(ADMIN_FAILURES)>=10
            if limited:self.reply(429,{'error':'管理登入失敗次數過多，請 5 分鐘後再試'});return
            supplied=self.headers.get('X-QA-Admin','')
            if not ADMIN_PASSWORD or not secrets.compare_digest(supplied,ADMIN_PASSWORD):
                with qa.LOCK:ADMIN_FAILURES.append(now)
                self.reply(403,{'error':'請輸入正確的報告者管理密碼'});return
            if not origin or not secrets.compare_digest(self.headers.get('X-QA-Session',''),qa.TOKEN):
                self.reply(403,{'error':'請重新開啟管理頁'});return
            if path=='/api/close':
                with qa.LOCK:OPEN_UNTIL=0;qa.API_KEY='';qa.CACHE.clear()
                self.reply(200,{'closed':True,'note':'已關閉新提問並清除金鑰；已送往 Google 的請求可能仍會完成。'});return
            if path=='/api/config':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=8192:raise ValueError()
                    data=json.loads(self.rfile.read(length));key=data.get('api_key','').strip()
                    if not re.fullmatch(r'[A-Za-z0-9._~+/=-]{20,4096}',key):raise ValueError()
                except (ValueError,TypeError,AttributeError):
                    self.reply(400,{'error':'請貼上完整 Gemini 金鑰，不可包含空白、引號或網址'});return
                if not qa.GATE.acquire(blocking=False):self.reply(409,{'error':'模型忙碌中，請稍後再設定'});return
                try:
                    with qa.LOCK:
                        qa.API_KEY=key;qa.PROVIDER='gemini';qa.CACHE.clear();OPEN_UNTIL=time.time()+7200
                    self.reply(200,{'configured':True,'expires_at':int(OPEN_UNTIL),'note':'課堂已開放 2 小時；請驗證連線並實際試問。'})
                finally:qa.GATE.release()
                return
            if not qa.API_KEY:self.reply(400,{'error':'尚未設定 Gemini 金鑰'});return
            request=Request(f'https://generativelanguage.googleapis.com/v1beta/models/{qa.MODEL}',headers={'x-goog-api-key':qa.API_KEY})
            try:
                with urlopen(request,timeout=20) as r:r.read(10000)
                self.reply(200,{'verified':True,'note':'金鑰與模型查詢通過；生成額度仍須實際提問確認。'})
            except HTTPError as e:
                self.reply(503,{'error':f'Google 回應 HTTP {e.code}。請檢查金鑰、模型權限、所在地區或額度。','provider_status':e.code})
            except (URLError,OSError):self.reply(503,{'error':'無法連上 Google，請稍後再試。'})
            return
        if path=='/api/qa' and (time.time()>=OPEN_UNTIL or not qa.API_KEY):
            self.reply(403,{'error':'課堂問答尚未開放或已結束，仍可使用離線來源查詢。'});return
        super().do_POST()

if __name__=='__main__':
    server=qa.ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),CloudHandler)
    print('Cloud classroom service starting: '+VERSION,flush=True)
    server.serve_forever()
