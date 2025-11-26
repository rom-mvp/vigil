"""Lightweight static file server for the Vigil console."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HOST = "0.0.0.0"
PORT = 3000


def main() -> None:
    """Serve the web directory using Python's stdlib HTTP server."""

    class VigilRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    server = ThreadingHTTPServer((HOST, PORT), VigilRequestHandler)
    print(f"Vigil dev server running at http://localhost:{PORT}", flush=True)
    print(f"Serving files from: {BASE_DIR}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down Vigil dev server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
