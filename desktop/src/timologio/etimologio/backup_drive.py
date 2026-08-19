"""Αντίγραφα ασφαλείας του e-Τιμολόγιο, με προορισμό το Google Drive.

Γιατί υπάρχει
-------------
Η βάση και το ``.enckey`` ζουν σε έναν υπολογιστή γραφείου. Ένας δίσκος που
χάλασε παίρνει μαζί του κάθε παραστατικό, κάθε πληρωμή και — χειρότερα — τα
**κλειδιά ΑΑΔΕ κάθε πελάτη**, που δεν ανακτώνται από πουθενά.

Πώς δένει με τα υπόλοιπα
------------------------
Ακολουθεί το ίδιο μοτίβο με το ScanmyData: τα μυστικά **δεν** ζουν σε αρχείο
ρυθμίσεων· έρχονται από **Infisical** στην εκκίνηση και μπαίνουν σε μεταβλητές
περιβάλλοντος. Η μεταφόρτωση γίνεται με OAuth **χρήστη** (refresh token), όχι
service account, ώστε ο φάκελος να ανήκει σε πραγματικό λογαριασμό Drive.

Κατάσταση: **έτοιμο έδαφος**. Το πακετάρισμα, το κλάδεμα και οι ρυθμίσεις
δουλεύουν και δοκιμάζονται εδώ· η μεταφόρτωση απαιτεί τις βιβλιοθήκες Google
(``pip install .[drive]``) και συμπληρωμένα μυστικά. Χωρίς αυτά το ``status()``
λέει ακριβώς τι λείπει και δεν επιχειρεί τίποτα — δεν υπάρχει «μισό» αντίγραφο
που νομίζεις ότι έγινε.
"""

from __future__ import annotations

import logging
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

#: Ο φάκελος στο Drive. Ένας ανά εγκατάσταση.
ROOT_FOLDER_NAME = "eTimologio_backups"

#: Τα μυστικά που χρειάζονται, με τα ονόματα που έχουν και στο ScanmyData ώστε
#: το ίδιο project του Infisical να εξυπηρετεί και τις δύο εφαρμογές.
REQUIRED_SECRETS = (
    "google_client_id",
    "google_client_secret",
    "google_drive_refresh_token",
)

#: Τι μπαίνει στο αρχείο. Το ``.enckey`` είναι το ΠΙΟ κρίσιμο: χωρίς αυτό η
#: βάση είναι θόρυβος. Μπαίνει μαζί επίτηδες — ένα αντίγραφο που δεν διαβάζεται
#: δεν είναι αντίγραφο.
BACKUP_MEMBERS = ("local.sqlite", ".enckey", "service.json")


@dataclass(frozen=True)
class DriveStatus:
    """Τι λείπει για να δουλέψει η μεταφόρτωση."""

    libraries: bool
    secrets: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.libraries and not self.secrets

    @property
    def problem(self) -> str:
        if not self.libraries:
            return ("Λείπουν οι βιβλιοθήκες Google Drive "
                    "(εγκατάσταση: pip install .[drive]).")
        if self.secrets:
            return "Λείπουν μυστικά από το Infisical: " + ", ".join(self.secrets)
        return ""


def _libraries_present() -> bool:
    try:
        import googleapiclient  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
    except Exception:  # noqa: BLE001 — απούσα προαιρετική εξάρτηση
        return False
    return True


def status() -> DriveStatus:
    """Είναι έτοιμη η μεταφόρτωση; Αν όχι, τι ακριβώς λείπει."""
    missing = tuple(n for n in REQUIRED_SECRETS if not os.environ.get(n, "").strip())
    return DriveStatus(libraries=_libraries_present(), secrets=missing)


def bootstrap_secrets(timeout_seconds: int = 10) -> bool:
    """Φέρνει τα μυστικά από το Infisical στο περιβάλλον.

    Ίδιο συμβόλαιο με το ScanmyData: θέλει ``INFISICAL_TOKEN``,
    ``INFISICAL_PROJECT_ID`` και ``INFISICAL_ENVIRONMENT`` ήδη στο περιβάλλον.
    Επιστρέφει ``False`` (χωρίς εξαίρεση) όταν δεν είναι ρυθμισμένο — μια
    εγκατάσταση χωρίς Infisical πρέπει να ξεκινά κανονικά.
    """
    token = os.environ.get("INFISICAL_TOKEN", "").strip()
    project = os.environ.get("INFISICAL_PROJECT_ID", "").strip()
    env_name = os.environ.get("INFISICAL_ENVIRONMENT", "").strip()
    if not (token and project and env_name):
        log.info("Infisical: δεν είναι ρυθμισμένο — παραλείπεται")
        return False
    base = (os.environ.get("INFISICAL_BASE_URL") or "https://app.infisical.com").rstrip("/")
    try:
        import requests

        reply = requests.get(
            base + "/api/v3/secrets/raw",
            headers={"Authorization": "Bearer " + token},
            params={
                "workspaceId": project,
                "environment": env_name,
                "secretPath": os.environ.get("INFISICAL_SECRET_PATH", "/"),
            },
            timeout=timeout_seconds,
        )
        reply.raise_for_status()
        payload = reply.json()
    except Exception as exc:  # noqa: BLE001 — δίκτυο ή διαπιστευτήρια
        log.warning("Infisical: αποτυχία ανάκτησης μυστικών (%s)", exc)
        return False
    count = 0
    for item in payload.get("secrets") or []:
        key = item.get("secretKey") or item.get("key")
        value = item.get("secretValue")
        if key and value is not None:
            os.environ[str(key)] = str(value)
            count += 1
    log.info("Infisical: φορτώθηκαν %d μυστικά", count)
    return count > 0


def build_archive(data_dir: Path, target_dir: Path | None = None) -> Path:
    """Πακετάρει βάση + κλειδί σε ένα zip και επιστρέφει τη διαδρομή του.

    Δουλεύει ΧΩΡΙΣ δίκτυο και χωρίς Google: το τοπικό αρχείο είναι από μόνο του
    χρήσιμο (αντιγραφή σε USB), και είναι το ίδιο που θα ανέβει.
    """
    data_dir = Path(data_dir)
    target_dir = Path(target_dir) if target_dir else data_dir / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = target_dir / ("etimologio-" + stamp + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in BACKUP_MEMBERS:
            source = data_dir / name
            if source.is_file():
                bundle.write(source, name)
        # Το WAL κρατά εγγραφές που δεν πέρασαν ακόμη στο κύριο αρχείο.
        for extra in ("local.sqlite-wal", "local.sqlite-shm"):
            source = data_dir / extra
            if source.is_file():
                bundle.write(source, extra)
    log.info("Αντίγραφο: %s (%d bytes)", archive, archive.stat().st_size)
    return archive


def prune_old(target_dir: Path, keep: int = 14) -> int:
    """Κρατά τα `keep` νεότερα αρχεία· επιστρέφει πόσα διαγράφηκαν."""
    target_dir = Path(target_dir)
    if not target_dir.is_dir():
        return 0
    files = sorted(
        target_dir.glob("etimologio-*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for old in files[keep:]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def upload(archive: Path) -> str:
    """Ανεβάζει το αρχείο στο Drive· επιστρέφει το id του.

    Σηκώνει ``RuntimeError`` με **συγκεκριμένη** αιτία όταν κάτι λείπει, αντί
    να αποτύχει σιωπηλά: ένα αντίγραφο που νομίζεις ότι έγινε είναι χειρότερο
    από κανένα.
    """
    state = status()
    if not state.ready:
        raise RuntimeError(state.problem)

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        None,
        refresh_token=os.environ["google_drive_refresh_token"],
        client_id=os.environ["google_client_id"],
        client_secret=os.environ["google_client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder_id = _ensure_folder(service, ROOT_FOLDER_NAME)
    media = MediaFileUpload(str(archive), mimetype="application/zip", resumable=True)
    created = service.files().create(
        body={"name": archive.name, "parents": [folder_id]},
        media_body=media,
        fields="id",
    ).execute()
    return str(created.get("id", ""))


def _ensure_folder(service, name: str) -> str:
    query = (
        "mimeType='application/vnd.google-apps.folder' and trashed=false "
        "and name='" + name + "'"
    )
    found = service.files().list(q=query, fields="files(id)", pageSize=1).execute()
    files = found.get("files") or []
    if files:
        return str(files[0]["id"])
    created = service.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return str(created["id"])


def run_backup(data_dir: Path, *, keep: int = 14, to_drive: bool = True) -> dict:
    """Πλήρης κύκλος: πακετάρισμα → (προαιρετικά) ανέβασμα → κλάδεμα."""
    archive = build_archive(data_dir)
    result = {
        "archive": str(archive),
        "size": archive.stat().st_size,
        "uploaded": "",
        "error": "",
    }
    if to_drive:
        try:
            result["uploaded"] = upload(archive)
        except Exception as exc:  # noqa: BLE001 — φτάνει στο UI ως μήνυμα
            result["error"] = str(exc)
            log.warning("Το ανέβασμα στο Drive απέτυχε: %s", exc)
    result["pruned"] = prune_old(archive.parent, keep)
    return result


__all__ = [
    "DriveStatus", "status", "bootstrap_secrets", "build_archive",
    "prune_old", "upload", "run_backup", "ROOT_FOLDER_NAME", "REQUIRED_SECRETS",
]
