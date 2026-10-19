"""Exercise the actual deployed API, leaving one resolved test record."""
import argparse
import json
from urllib.request import Request, urlopen
import uuid


def run(base):
    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(base.rstrip('/')+path, data=data, headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=15) as response:
            return response.status, json.load(response)
    assert request('/health/live')[0] == 200
    assert request('/health/ready')[0] == 200
    title = 'Smoke test '+uuid.uuid4().hex[:8]
    code, item = request('/api/checks', {'title': title})
    assert code == 201 and item['title'] == title
    records = request('/api/checks')[1]['items']
    assert any(x['id'] == item['id'] for x in records)
    code, resolved = request(f"/api/checks/{item['id']}/resolve", {})
    assert code == 200 and resolved['status'] == 'resolved'
    print('PASS: liveness, readiness, create, persistence read, and resolve')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8088')
    run(parser.parse_args().base_url)
