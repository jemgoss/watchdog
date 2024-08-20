
import logging
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
from http import HTTPStatus
import socket
import threading
import sys
import os

EXIT_CODE_OK = 0
EXIT_CODE_UNCAUGHT_EXCEPTON = 1001
EXIT_CODE_RESTART = 1002
EXIT_CODE_NETWORK = 1003

from types import SimpleNamespace
main_worker = SimpleNamespace(
    condition = threading.Condition(),
    terminated = False,
    notify_socket = None,
    exit_code = 0,
    )

def get_notify_socket():
    addr = os.getenv('NOTIFY_SOCKET')
    if addr:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        if addr[0] == '@':
            addr = '\0' + addr[1:]
        s.connect(addr)
        return s

class WatchdogHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 15 # request socket timeout

    def do_GET(self):
        # print("C,P,V:", self.command, self.path, self.request_version)
        # print(self.headers)
        super().do_GET()

    def do_POST(self):
        # print("C,P,V:", self.command, self.path, self.request_version)
        # print(self.headers)
        if self.path == "/api/ping":
            self.close_connection = True
            self.send_content(b"pong", "text/plain")
            with main_worker.condition:
                if main_worker.notify_socket:
                    main_worker.notify_socket.sendall(b"WATCHDOG=1")
        elif self.path == "/api/shutdown":
            self.log_message("Shutting down...")
            self.close_connection = True
            self.send_content(b"ok", "text/plain")
            self.exit(EXIT_CODE_OK)
        elif self.path == "/api/restart":
            self.log_message("Restarting...")
            self.close_connection = True
            self.send_content(b"ok", "text/plain")
            self.exit(EXIT_CODE_RESTART)
        elif self.path == "/api/enableNotify":
            self.close_connection = True
            self.send_content(b"ok", "text/plain")
            with main_worker.condition:
                if main_worker.notify_socket is None:
                    main_worker.notify_socket = get_notify_socket()
        elif self.path == "/api/disableNotify":
            self.close_connection = True
            self.send_content(b"ok", "text/plain")
            with main_worker.condition:
                if main_worker.notify_socket is not None:
                    main_worker.notify_socket.close()
                    main_worker.notify_socket = None

    def exit(self, exit_code):
        # Notify the main_worker thread that we want to exit.
        with main_worker.condition:
            main_worker.terminated = True
            main_worker.exit_code = exit_code
            main_worker.condition.notify_all()

    def send_content(self, content, mimeType):
        self.send_response(HTTPStatus.OK)
        #self.send_header("Expires", "-1")
        self.send_header("Cache-Control", "max-age=0,no-cache") # dynamic content
        self.send_header("Content-Type", mimeType)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

def ping():
    conn = HTTPConnection("localhost", 9080, timeout=5)
    try:
        conn.request("POST", "/api/ping")
        res = conn.getresponse()
        if res.status != HTTPStatus.OK or res.read() != b"pong":
            print("ping failed")
            # with main_worker.condition:
            #     if main_worker.notify_socket:
            #         main_worker.notify_socket.sendall(b"WATCHDOG=trigger")
    finally:
        conn.close()

def main():
    with main_worker.condition:
        main_worker.notify_socket = get_notify_socket()

    ping_interval = 10
    interval_usec = os.getenv("WATCHDOG_USEC")
    if interval_usec:
        ping_interval = int(interval_usec)/2000000 # half watchdog interval (in secs)

    exit_code = EXIT_CODE_UNCAUGHT_EXCEPTON
    with ThreadingHTTPServer(("", 9080), WatchdogHandler) as http_svr:
        sa = http_svr.socket.getsockname()
        logging.info("Serving HTTP on %s port %d...", sa[0], sa[1])

        threading.Thread(
            name = "HTTPThread",
            target = http_svr.serve_forever,
            kwargs = {"poll_interval" : 5},
            daemon=True).start()

        with main_worker.condition:
            if main_worker.notify_socket:
                main_worker.notify_socket.sendall(b"READY=1")

        try:
            with main_worker.condition:
                while not main_worker.terminated:
                    if not main_worker.condition.wait(ping_interval):
                        ping()
            exit_code = main_worker.exit_code
        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received.")
        finally:
            logging.info("Shutting down HTTP server...")
            http_svr.shutdown()
    logging.info("Done.")
    logging.shutdown()
    return exit_code

if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s: %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        handlers=None,
        level=logging.DEBUG)
    sys.exit(main())
