import logging
import os
import queue
import time
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text

log = logging.getLogger(__name__)

# time to wait before retrying a failed upload (seconds).
_RETRY_DELAY = 5


class UploaderThread:

    """Drains an in-memory queue of snapshot paths, uploading each to S3.

    On failure, waits _RETRY_DELAY seconds and re-enqueues the item. The file is
    never deleted here — it stays in /data/snapshots/ until it is cleaned up manually.
    This satisfies the "local fallback" requirement: if S3 is unreachable the
    files accumulate locally and drain when connectivity returns. Anything still
    pending when the app restarts is re-queued from the database on startup (main.py).

    Not a Thread subclass, started via thread = threading.Thread(target=uploader.run).
    Using composition instead of inheritance makes it easier to pass the uploader
    object around without exposing thread internals.
    """

    def __init__(self, state, stop_event, db_engine) -> None:
        self._state = state
        self._stop = stop_event
        self._engine = db_engine
        self._queue: queue.Queue[tuple[Path, int]] = queue.Queue()
        self._bucket = os.environ["S3_BUCKET"]

        # boto3 uses the default credential chain: env vars  → ~/.aws/config →
        # instance metadata. This means switching to IAM Roles Anywhere later
        # is purely a deployment change — no code change needed later from my end
        self._s3 = boto3.client("s3")

    def enqueue(self, path: Path, event_id: int) -> None:
        self._queue.put((path, event_id))
        self._state.update(upload_queue_depth=self._queue.qsize())

    def run(self) -> None:
        log.info("Uploader started, bucket=%s", self._bucket)
        while not self._stop.is_set():
            try:
                path, event_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._upload(path, event_id)
            except Exception:
                # anything unexpected (e.g. db error) - log it and keep the thread alive.
                # the event stays s3_uploaded=False so it gets re-queued on next restart
                log.exception("Unexpected error uploading %s", path.name)
            self._state.update(upload_queue_depth=self._queue.qsize())

    def _upload(self, path: Path, event_id: int) -> None:
        if not path.exists():
            log.warning("Snapshot %s no longer exists, skipping upload", path)
            return
        key = "snapshots/" + "/".join(path.parts[-5:])  # YYYY/MM/DD/HH/filename.jpg
        try:
            self._s3.upload_file(
                str(path),
                self._bucket,
                key,
                ExtraArgs={"ServerSideEncryption": "AES256"},
            )
            log.info("Uploaded %s → s3://%s/%s", path.name, self._bucket, key)
            self._state.update(uploader_status="ok")
            self._mark_uploaded(event_id)
        except (BotoCoreError, ClientError) as exc:
            log.error("S3 upload failed for %s: %s", path.name, exc)
            self._state.update(uploader_status="offline")
            time.sleep(_RETRY_DELAY)
            self._queue.put((path, event_id))  # re enqueue for retry

    def _mark_uploaded(self, event_id: int) -> None:
        with self._engine.connect() as conn:
            conn.execute(
                text("UPDATE events SET s3_uploaded = TRUE WHERE id = :id"),
                {"id": event_id},
            )
            conn.commit()
