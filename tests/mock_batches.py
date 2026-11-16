import json, re, sys, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
B={}
def tr(prompt):
    payload=json.loads(prompt[prompt.rindex('\n[')+1:] if '\n[' in prompt else prompt[prompt.index('['):])
    out=[]
    for d in payload:
        toks=re.findall(r'⟦\d+⟧', d['en']); lines=d['en'].split('\n')
        es='\n'.join(' '.join('palabra' for _ in l.split()) for l in lines)
        out.append({"id":d['id'],"es":(es+' '+' '.join(toks)).strip() if toks else es or 'palabra'})
    return json.dumps({"t":out},ensure_ascii=False)
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _send(self,code,body,ct='application/json'):
        b=body.encode() if isinstance(body,str) else body
        self.send_response(code); self.send_header('Content-Type',ct); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        bid='msgbatch_'+uuid.uuid4().hex[:8]; B[bid]=body['requests']
        self._send(200,json.dumps({"id":bid,"processing_status":"in_progress"}))
    def do_GET(self):
        p=self.path.split('/')
        if p[-1]=='results':
            bid=p[-2]; lines=[]
            for r in B[bid]:
                txt=tr(r['params']['messages'][0]['content'])
                lines.append(json.dumps({"custom_id":r['custom_id'],"result":{"type":"succeeded","message":{"content":[{"type":"text","text":txt}]}}},ensure_ascii=False))
            self._send(200,'\n'.join(lines))
        else:
            bid=p[-1]; self._send(200,json.dumps({"id":bid,"processing_status":"ended","results_url":f"http://127.0.0.1:{PORT}/v1/messages/batches/{bid}/results"}))
PORT=int(sys.argv[1]); ThreadingHTTPServer(('127.0.0.1',PORT),H).serve_forever()
