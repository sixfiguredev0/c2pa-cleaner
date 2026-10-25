"""
C2PA Cleaner — Desktop Entrypoint & Local Launcher
Starts the local-first loopback server and opens the browser interface.
"""

import socket
import sys
import threading
import time
import webbrowser
import uvicorn

from app.backend.server import app


def find_available_port(start_port: int = 8000, max_attempts: int = 100) -> int:
    """Find an available TCP port bound to 127.0.0.1."""
    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start_port


def open_browser_delayed(url: str, delay_seconds: float = 0.8):
    """Wait for the server to bind and open the user's default browser."""
    time.sleep(delay_seconds)
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[!] Could not automatically open browser: {e}")
        print(f"[*] Please open {url} in your browser manually.")


def main():
    host = "127.0.0.1"
    port = find_available_port(8000)
    url = f"http://{host}:{port}"

    print("=" * 60)
    print("  C2PA Cleaner — Local Provenance Metadata Remover")
    print("  Running locally on loopback interface (zero cloud uploads)")
    print(f"  URL: {url}")
    print("=" * 60)

    # Launch browser in background thread
    threading.Thread(target=open_browser_delayed, args=(url, 0.8), daemon=True).start()

    # Start FastAPI / Uvicorn server
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n[*] Shutting down C2PA Cleaner server cleanly...")
        sys.exit(0)


if __name__ == "__main__":
    main()
