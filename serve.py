#!/usr/bin/env python3
"""
Simple HTTP server with a /api/refresh endpoint to trigger the job fetcher.
Serves static files from the project root (web/ and data/ directories).
"""

import json
import os
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Add fetch/ to path so we can import the fetcher
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'fetch'))
from fetcher import run_fetch, DATA_DIR

_refresh_lock = threading.Lock()
_refreshing = False


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/refresh':
            self.handle_refresh()
        else:
            self.send_error(404)

    def handle_refresh(self):
        global _refreshing

        if not _refresh_lock.acquire(blocking=False):
            self.send_json(409, {'status': 'busy', 'message': 'Refresh already in progress'})
            return

        try:
            _refreshing = True
            run_fetch()

            # Read metadata for response
            meta_path = DATA_DIR / 'metadata.json'
            with open(meta_path, 'r') as f:
                metadata = json.load(f)

            self.send_json(200, {
                'status': 'ok',
                'totalJobs': metadata.get('totalJobs', 0),
                'newJobs': metadata.get('newSinceLastRefresh', 0),
            })
        except Exception as e:
            self.send_json(500, {'status': 'error', 'message': str(e)})
        finally:
            _refreshing = False
            _refresh_lock.release()

    def send_json(self, code, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress noisy static file logs, keep API logs
        if '/api/' in (args[0] if args else ''):
            super().log_message(format, *args)


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    server = HTTPServer(('', port), Handler)
    print(f'Serving on http://localhost:{port}/web/')
    print('Press Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
