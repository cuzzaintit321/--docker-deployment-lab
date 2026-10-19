"""Small HTTP API for a Docker/PostgreSQL deployment lab."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import re

LOG = logging.getLogger('deployment-lab')


class PostgresStore:
    def connection(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(host=os.getenv('DB_HOST', 'db'),
                               dbname=os.getenv('DB_NAME', 'operations'),
                               user=os.getenv('DB_USER', 'operations'),
                               password=os.environ['DB_PASSWORD'],
                               connect_timeout=3, options='-c statement_timeout=3000',
                               row_factory=dict_row)

    def ready(self):
        with self.connection() as conn:
            conn.execute('SELECT id FROM checks LIMIT 1').fetchall()

    def list(self):
        with self.connection() as conn:
            return conn.execute('SELECT id, title, status, created_at FROM checks ORDER BY id DESC LIMIT 100').fetchall()

    def add(self, title):
        with self.connection() as conn:
            return conn.execute("INSERT INTO checks(title) VALUES (%s) RETURNING id, title, status, created_at", (title,)).fetchone()

    def resolve(self, item_id):
        with self.connection() as conn:
            return conn.execute("UPDATE checks SET status = 'resolved' WHERE id = %s RETURNING id, title, status, created_at", (item_id,)).fetchone()


def handler_for(store):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload):
            body = json.dumps(payload, default=str).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                if self.path == '/health/live':
                    self.reply(200, {'status': 'alive'})
                elif self.path == '/health/ready':
                    store.ready()
                    self.reply(200, {'status': 'ready'})
                elif self.path == '/api/checks':
                    self.reply(200, {'items': store.list()})
                else:
                    self.reply(404, {'error': 'Not found'})
            except Exception:
                LOG.warning('Database operation failed on GET %s', self.path)
                self.reply(503, {'error': 'Database unavailable'})

        def do_POST(self):
            self.connection.settimeout(5)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0 or length > 4096:
                    self.reply(413, {'error': 'Request too large'})
                    return
                if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                    self.reply(415, {'error': 'Use application/json'})
                    return
                raw = self.rfile.read(length)
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError('Object required')
            except (ValueError, UnicodeDecodeError, TimeoutError, OSError):
                self.reply(400, {'error': 'Invalid JSON request'})
                return
            try:
                if self.path == '/api/checks':
                    title = body.get('title')
                    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
                        self.reply(400, {'error': 'Title must contain 1–160 characters'})
                        return
                    self.reply(201, store.add(title.strip()))
                elif match := re.fullmatch(r'/api/checks/([1-9][0-9]{0,8})/resolve', self.path):
                    item = store.resolve(int(match.group(1)))
                    self.reply(200 if item else 404, item or {'error': 'Check not found'})
                else:
                    self.reply(404, {'error': 'Not found'})
            except Exception:
                LOG.warning('Database operation failed on POST %s', self.path)
                self.reply(503, {'error': 'Database unavailable'})

        def log_message(self, fmt, *args):
            LOG.info(fmt, *args)
    return Handler


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    server = ThreadingHTTPServer(('0.0.0.0', 8000), handler_for(PostgresStore()))
    LOG.info('API listening on port 8000')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
