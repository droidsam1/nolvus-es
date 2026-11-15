"""Servidor que imita /api/chat de Ollama para probar el motor sin GPU.
Devuelve cada texto con palabras españolas añadidas y las fichas ⟦n⟧ intactas.
Con FAIL_EVERY=n, rompe una ficha cada n textos para probar los reintentos."""
import json, os, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FAIL_EVERY = int(os.environ.get("FAIL_EVERY", "0"))
count = 0

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        global count
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = body["messages"][-1]["content"]
        items = json.loads(user[user.rindex("\n[") + 1:]) if "\n[" in user else json.loads(user[user.index("["):])
        out = []
        for it in items:
            count += 1
            es = re.sub(r"(?<![⟦\d])[A-Za-z']+", "palabra", it["en"]) + " de la"
            if FAIL_EVERY and count % FAIL_EVERY == 0:
                es = re.sub(r"⟦\d+⟧", "", es, count=1) if "⟦" in es else ""
            out.append({"id": it["id"], "es": es})
        time.sleep(0.05)
        resp = json.dumps({"message": {"content": json.dumps({"t": out}, ensure_ascii=False)}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(resp)

ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 11999), H).serve_forever()
