"""Single-process production entry point: bounded threads, in-process processing queue."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from waitress import serve
from app import create_app

if __name__ == '__main__':
    serve(create_app(), host=os.environ.get('STUDIO_BIND', '127.0.0.1'),
          port=int(os.environ.get('STUDIO_PORT', '8765')), threads=6,
          max_request_body_size=85 * 1024 * 1024,
          channel_timeout=120, connection_limit=8,
          ident='Studio', expose_tracebacks=False)
