#!/usr/bin/env python3
"""
serve_jam.py — Persistent local HTTP server for the Formula Fun 6'0" Jam Surfboard 3D & AR Review Showcase.
Serves on 127.0.0.1:8099 with RFC-7233 HTTP 206 Partial Content (Range) support for iOS/macOS Safari <video>
streaming, plus Apple AR Quick Look (model/vnd.usdz+zip) and WebGL (model/gltf-binary) MIME types.
"""

import http.server
import socketserver
import os
import re
import mimetypes

PORT = 8099
HOST = "127.0.0.1"
SERVE_DIR = "/Volumes/T9/Workspace/projects/Formula Fun/3D Product Files/Jam_60_CAD"

mimetypes.add_type("model/vnd.usdz+zip", ".usdz")
mimetypes.add_type("model/gltf-binary", ".glb")
mimetypes.add_type("model/gltf+json", ".gltf")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("text/html", ".html")


class RangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SERVE_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            for index in ("index.html", "index.htm"):
                index_path = os.path.join(path, index)
                if os.path.exists(index_path):
                    path = index_path
                    break
            else:
                return self.list_directory(path)

        ctype = self.guess_type(path)
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        fs = os.fstat(f.fileno())
        file_len = fs[6]
        range_header = self.headers.get("Range")

        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if m:
                start_str, end_str = m.groups()
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_len - 1
                end = min(end, file_len - 1)
                if start > end or start >= file_len:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    f.close()
                    return None
                self.send_response(206)
                self.send_header("Content-type", ctype)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_len}")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                self.end_headers()
                f.seek(start)
                self._range_bytes_left = end - start + 1
                return f

        self._range_bytes_left = None
        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", str(file_len))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return f

    def copyfile(self, source, outputfile):
        if getattr(self, "_range_bytes_left", None) is not None:
            left = self._range_bytes_left
            bufsize = 64 * 1024
            while left > 0:
                chunk = source.read(min(bufsize, left))
                if not chunk:
                    break
                outputfile.write(chunk)
                left -= len(chunk)
        else:
            super().copyfile(source, outputfile)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_server():
    os.chdir(SERVE_DIR)
    with ThreadingHTTPServer((HOST, PORT), RangeHTTPRequestHandler) as httpd:
        print(f"Formula Fun 6'0\" Jam 3D Showcase serving with HTTP 206 Range at http://{HOST}:{PORT}/", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    run_server()
