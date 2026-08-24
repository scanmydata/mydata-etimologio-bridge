"""Παίρνει refresh token για το Google Drive, χωρίς εξαρτήσεις.

    python tools/google_refresh_token.py <CLIENT_ID> <CLIENT_SECRET>

Ανοίγει τον browser, περιμένει να πατήσεις «Να επιτραπεί», και τυπώνει το
refresh token. Αυτό είναι που μπαίνει στο Infisical ως
``GOOGLE_DRIVE_REFRESH_TOKEN_SCANMYDATA_SUITE``.

ΓΙΑΤΙ ΤΟΠΙΚΑ ΚΑΙ ΟΧΙ ΣΤΟΝ SERVER: η συγκατάθεση είναι πράξη ΤΟΥ ΚΑΤΟΧΟΥ του
Drive — πρέπει να γίνει στον browser όπου είναι συνδεδεμένος, και το client
secret δεν χρειάζεται να ταξιδέψει πουθενά αλλού. Το token που βγαίνει είναι το
μόνο που φεύγει από αυτόν τον υπολογιστή, και πάει στο Infisical.

ΓΙΑΤΙ ΠΛΗΡΕΣ `drive` ΚΑΙ ΟΧΙ `drive.file`: το `drive.file` βλέπει μόνο αρχεία
που δημιούργησε η ίδια η εφαρμογή — δεν θα έβρισκε ποτέ τον φάκελο που έφτιαξες
εσύ με το χέρι, και θα έφτιαχνε δεύτερο ομώνυμο. Με πλήρες `drive` τα αντίγραφα
πάνε ΕΚΕΙ που τα θέλεις. Αν προτιμάς τη στενότερη κλίμακα, τρέξε το με
`--scope drive.file` και άσε την εφαρμογή να φτιάξει μόνη της τον φάκελο.
"""

from __future__ import annotations

import argparse
import http.server
import json
import secrets
import socket
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = {
    "drive": "https://www.googleapis.com/auth/drive",
    "drive.file": "https://www.googleapis.com/auth/drive.file",
}

_result: dict[str, str] = {}
_done = threading.Event()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — το όνομα το ορίζει η βιβλιοθήκη
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _result.update({k: v[0] for k, v in params.items()})
        body = (
            "<html><body style='font-family:sans-serif;padding:40px'>"
            "<h2>Έτοιμο.</h2><p>Κλείσε αυτή την καρτέλα και γύρνα στο τερματικό.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        _done.set()

    def log_message(self, *args) -> None:   # χωρίς θόρυβο στο τερματικό
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("client_id")
    ap.add_argument("client_secret")
    ap.add_argument("--scope", choices=sorted(SCOPES), default="drive")
    args = ap.parse_args()

    port = free_port()
    redirect = f"http://127.0.0.1:{port}"
    state = secrets.token_urlsafe(16)

    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": args.client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPES[args.scope],
        # ΚΡΙΣΙΜΑ ΚΑΙ ΤΑ ΔΥΟ: χωρίς `offline` δεν δίνεται refresh token, και
        # χωρίς `prompt=consent` το Google το παραλείπει σε κάθε ΕΠΟΜΕΝΗ
        # εξουσιοδότηση του ίδιου λογαριασμού — παίρνεις μόνο access token και
        # ψάχνεις γιατί «δεν βγαίνει refresh token».
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("Ανοίγει ο browser. Διάλεξε τον λογαριασμό του Drive και πάτησε «Να επιτραπεί».")
    print(f"Αν δεν ανοίξει μόνος του:\n  {url}\n")
    webbrowser.open(url)

    if not _done.wait(timeout=300):
        print("Έληξε ο χρόνος αναμονής (5 λεπτά).", file=sys.stderr)
        return 1
    server.shutdown()

    if _result.get("state") != state:
        print("Ασυμφωνία state — ακυρώνεται.", file=sys.stderr)
        return 1
    if "error" in _result:
        print("Η Google απάντησε: " + _result["error"], file=sys.stderr)
        return 1

    data = urllib.parse.urlencode({
        "code": _result.get("code", ""),
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data)) as resp:
        payload = json.loads(resp.read().decode())

    token = payload.get("refresh_token")
    if not token:
        print("Δεν ήρθε refresh token. Απάντηση: " + json.dumps(payload), file=sys.stderr)
        return 1

    print("\nREFRESH TOKEN (βάλ' το στο Infisical ως")
    print("GOOGLE_DRIVE_REFRESH_TOKEN_SCANMYDATA_SUITE):\n")
    print(token)
    print("\nΜην το αφήσεις σε αρχείο ή σε ιστορικό τερματικού.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
