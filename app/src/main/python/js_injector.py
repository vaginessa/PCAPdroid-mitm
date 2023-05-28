#!/usr/bin/env python3
#
#  This file is part of PCAPdroid.
#
#  PCAPdroid is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  PCAPdroid is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with PCAPdroid.  If not, see <http://www.gnu.org/licenses/>.
#
#  Copyright 2023 - Emanuele Faranda
#

# mitmdump --mode socks5 -p 8050 --flow-detail 0 -s js_injector.py
import os
from mitmproxy import http
from bs4 import BeautifulSoup
from modules.js_userscript import JsUserscript

class JsInjector:
    def __init__(self):
        self.scripts = []
        self.scripts_dir = os.path.join(os.path.dirname(__file__), "js")
        self.reload_scripts()

    def response(self, flow: http.HTTPFlow):
        #print(f"[{flow.response.status_code}] {flow.request.pretty_url}")

        # inject only for HTML resources
        constent_type = flow.response.headers.get("content-type", "")
        if constent_type and (not "text/html" in constent_type):
            return

        # https://docs.mitmproxy.org/stable/api/mitmproxy/http.html#HTTPFlow
        request =  flow.request
        script = None

        for s in self.scripts:
            if s.matches(request.scheme, request.pretty_host, request.path):
                script = s
                break

        if not script:
            return

        print(f"\"{script.name}\" script matches {request.pretty_url}")

        # IMPORTANT: delete these, otherwise it may upgrade the connection to QUIC
        # You may also need to block the QUIC protocol, as it seems like chrome still tries to use QUIC
        flow.response.headers.pop("alt-svc", None)
        flow.response.headers["alt-svc"] = "clear"

        # Remove error reporting
        flow.response.headers.pop("report-to", None)
        flow.response.headers.pop("nel", None)

        # Disable caching
        flow.response.headers["cache-control"] = "no-store"
        flow.response.headers["expires"] = "0"

        #print("Request Headers:" + str(flow.request.headers))
        #print("Response Headers:" + str(flow.response.headers))

        if not flow.response.content:
            # NOTE: even if cached (http 304), the above headers should invalidate it for the next request
            print(f"[{flow.response.status_code}] Response is empty (cached?)")
            return

        html = BeautifulSoup(flow.response.content, features="html.parser")
        if not html.body:
            print(f"Parsing HTML in {request.pretty_url} failed")
            return

        # Inject the script
        tag = html.new_tag("script", type="application/javascript")
        tag.insert(0, script.content)
        html.body.insert(0, tag)

        # Inject dependencies before the script
        for dep_js in reversed(script.require):
            tag = html.new_tag("script", type="text/javascript", src=dep_js)
            html.body.insert(0, tag)

        print(f"\"{script.name}\" script injected to {request.pretty_url}")
        flow.response.text = str(html)

    def reload_scripts(self):
        self.scripts = []

        try:
            for fname in os.listdir(self.scripts_dir):
                fpath = os.path.join(self.scripts_dir, fname)

                with open(fpath, "r") as f:
                    script = JsUserscript.parse(f)
                    if not script.name:
                        script.name = os.path.splitext(fname)[0]
                    print(f"Loaded \"{script.name}\" v{script.version}")
                    self.scripts.append(script)
        except os.FileNotFoundError:
            pass

if __name__ == "__main__":
    injector = JsInjector()
    injector.reload_scripts()
elif "addons" in locals():
    addons = [JsInjector()]