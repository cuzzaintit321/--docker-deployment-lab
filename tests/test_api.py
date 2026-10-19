from http.server import ThreadingHTTPServer
import json
import sys
from pathlib import Path
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from server import handler_for


class MemoryStore:
    def __init__(self):
        self.items = []
        self.available = True

    def ready(self):
        if not self.available:
            raise RuntimeError('Simulated database outage')

    def list(self):
        self.ready()
        return self.items

    def add(self, title):
        item = {'id': len(self.items)+1, 'title': title, 'status': 'open', 'created_at': 'test'}
        self.items.append(item)
        return item

    def resolve(self, item_id):
        for item in self.items:
            if item['id'] == item_id:
                item['status'] = 'resolved'
                return item


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.store))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, path, body=None, raw=None):
        data = json.dumps(body).encode() if body is not None else raw
        req = Request(self.base+path, data=data, headers={'Content-Type': 'application/json'})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.code, json.load(response)

    def test_create_list_resolve(self):
        code, item = self.request('/api/checks', {'title': 'Verify restore'})
        self.assertEqual(code, 201)
        self.assertEqual(self.request('/api/checks')[1]['items'][0]['title'], 'Verify restore')
        self.assertEqual(self.request(f"/api/checks/{item['id']}/resolve", {})[1]['status'], 'resolved')

    def test_invalid_json_and_empty_title(self):
        self.assertEqual(self.request('/api/checks', raw=b'{')[0], 400)
        self.assertEqual(self.request('/api/checks', {'title': '  '})[0], 400)
        self.assertEqual(self.request('/api/checks', {'title': 'a'*161})[0], 400)

    def test_missing_item_and_unknown_route(self):
        self.assertEqual(self.request('/api/checks/42/resolve', {})[0], 404)
        self.assertEqual(self.request('/arbitrary-file')[0], 404)

    def test_liveness_survives_outage_readiness_does_not(self):
        self.store.available = False
        self.assertEqual(self.request('/health/live')[0], 200)
        self.assertEqual(self.request('/health/ready')[0], 503)
        self.assertEqual(self.request('/api/checks')[0], 503)

    def test_oversized_body(self):
        self.assertEqual(self.request('/api/checks', raw=b'x'*4097)[0], 413)


if __name__ == '__main__':
    unittest.main()
