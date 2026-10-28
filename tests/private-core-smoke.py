#!/usr/bin/env python3
"""Exercise the actual private core with synthetic keys and loopback-only services."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    options = parser.parse_args()
    manifest = json.loads((ROOT / '.build/private-core-artifacts/manifest.json').read_text())
    binary = ROOT / manifest['binary']
    traffic = []
    provider_calls = []

    class Trap(BaseHTTPRequestHandler):
        def do_GET(self):
            traffic.append(self.path)
            self.send_error(502)
        do_POST = do_CONNECT = do_GET
        def log_message(self, *args):
            pass

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            provider_calls.append({'path': self.path, 'authorization': self.headers.get('Authorization'), 'body': payload})
            self.send_response(200)
            if payload.get('stream'):
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(b'data: {"id":"fixture","object":"chat.completion.chunk","model":"fixture-model","choices":[{"index":0,"delta":{"content":"local fixture"},"finish_reason":null}]}\n\ndata: [DONE]\n\n')
            else:
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'id':'fixture', 'object':'chat.completion', 'model':'fixture-model', 'choices':[{'index':0,'message':{'role':'assistant','content':'local fixture'},'finish_reason':'stop'}]}).encode())
        def log_message(self, *args):
            pass

    trap = ThreadingHTTPServer(('127.0.0.1', 0), Trap)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    for server in (trap, provider):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    client_key, management_key = secrets.token_hex(24), secrets.token_hex(24)
    def request(path, data=None, management=False):
        headers = {'Authorization': 'Bearer ' + (management_key if management else client_key)}
        if data is not None:
            data = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        try:
            with opener.open(urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data, headers=headers), timeout=5) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    with tempfile.TemporaryDirectory(prefix='private-core-smoke-') as temporary:
        home = Path(temporary)
        config = home / 'config.yaml'
        trap_url = f'http://127.0.0.1:{trap.server_port}'
        # Legacy spelling is intentionally supported by the core and tests migration/reload boundaries.
        contents = f'''host: 0.0.0.0
port: {port}
auth-dir: {home / 'oauth'}
api-keys: [{client_key}]
remote-management:
  secret-key: {management_key}
  allow-remote: true
  disable-control-panel: false
  disable-auto-update-panel: false
  panel-github-repository: {trap_url}/panel
plugins:
  enabled: true
  dir: {home / 'plugins'}
discovery:
  enabled: true
models:
  catalog: {trap_url}/catalog
  codex-catalog: {trap_url}/codex
  devin-catalog: {trap_url}/devin
openai-compatibility:
  - name: local-fixture
    base-url: http://127.0.0.1:{provider.server_port}/v1
    api-key-entries:
      - api-key: synthetic-upstream-key
        proxy-url: direct
    models:
      - name: fixture-model
'''
        config.write_text(contents)
        config.chmod(0o600)
        (home / '.env').write_text('HOME_JWT=not-a-real-token\nMANAGEMENT_PASSWORD=not-the-configured-key\n')
        env = {key: os.environ[key] for key in ('PATH','TMPDIR','SYSTEMROOT') if key in os.environ}
        env.update(HOME=str(home), HTTP_PROXY=trap_url, HTTPS_PROXY=trap_url, ALL_PROXY=trap_url,
                   HOME_JWT='invalid-synthetic-jwt', MANAGEMENT_PASSWORD='invalid-synthetic-key',
                   PGSTORE_DSN=f'postgres://synthetic@127.0.0.1:{trap.server_port}/fixture',
                   GITSTORE_GIT_URL=trap_url+'/git', OBJECTSTORE_ENDPOINT=trap_url)
        command = [str(binary), '-config', str(config), '--local-model']
        sandboxed = False
        if shutil.which('sandbox-exec'):
            profile = home / 'loopback.sb'
            profile.write_text('(version 1)\n(allow default)\n(deny network-outbound)\n(allow network-outbound (remote ip "localhost:*"))\n')
            command = ['sandbox-exec', '-f', str(profile), *command]
            sandboxed = True
        with (home / 'core.log').open('w+') as log:
            process = subprocess.Popen(command, cwd=home, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        log.seek(0)
                        raise AssertionError('Private core exited: ' + log.read())
                    try:
                        if request('/v1/models')[0] == 200:
                            break
                    except (OSError, urllib.error.URLError):
                        pass
                    if time.monotonic() > deadline:
                        log.seek(0)
                        raise AssertionError('Private core did not start: ' + log.read())
                    time.sleep(.1)
                time.sleep(2)
                assert not traffic and not provider_calls, (traffic, provider_calls)
                endpoints = {}
                for path in ('/management.html', '/v0/management/latest-version', '/v0/management/plugins/store'):
                    status, body = request(path, management=True)
                    endpoints[path] = status
                    assert status in (403, 404), (path, status, body)
                for streaming in (False, True):
                    status, body = request('/v1/chat/completions', {'model':'fixture-model','messages':[{'role':'user','content':'synthetic hello'}], 'stream':streaming})
                    assert status == 200 and 'local fixture' in body, (status, body)
                assert len(provider_calls) == 2, provider_calls
                for call in provider_calls:
                    assert call['path'] == '/v1/chat/completions' and call['authorization'] == 'Bearer synthetic-upstream-key', call
                    assert call['body']['messages'] == [{'role':'user','content':'synthetic hello'}], call
                config.write_text(contents + '\n# forced configuration reload\n')
                time.sleep(2)
                assert request('/v1/models')[0] == 200
                assert request('/management.html')[0] == 404
                assert not traffic, traffic
                result = {'passed':True,'binarySha256':manifest['binarySha256'], 'osLoopbackSandbox':sandboxed,
                          'idleAuxiliaryHTTPRequests':len(traffic), 'providerRequests':len(provider_calls),
                          'nonStreamingAndStreamingPassed':True, 'reloadPassed':True,'managementEndpoints':endpoints,
                          'realAccountsUsed':False, 'idleObservationSeconds':2, 'reloadObservationSeconds':2}
                if options.output:
                    options.output.write_text(json.dumps(result, indent=2)+'\n')
                print(json.dumps(result, indent=2))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    trap.shutdown()
    provider.shutdown()


if __name__ == '__main__':
    main()
