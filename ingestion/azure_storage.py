"""Thin wrapper over Azure Blob Storage.

An ADLS Gen2 account (hierarchical namespace on) also serves the Blob API, so one small
client covers the raw archive and the extracts container. Everything here is optional:
`is_configured()` is False unless an account (or an Azurite connection string for tests)
is set, and the rest of the pipeline then behaves exactly as it did before Azure existed.

Authentication:
- In Azure: `AZURE_STORAGE_ACCOUNT` plus a managed identity (`DefaultAzureCredential`;
  set `AZURE_CLIENT_ID` for a user-assigned identity). No keys or secrets anywhere.
- Locally / in tests: `AZURE_STORAGE_CONNECTION_STRING` (for example Azurite's).
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)
# The SDK logs every HTTP request and response at INFO, which would flood the job logs.
logging.getLogger("azure").setLevel(logging.WARNING)

DEFAULT_RAW_CONTAINER = "raw"
DEFAULT_EXTRACTS_CONTAINER = "extracts"


@dataclass(frozen=True)
class BlobInfo:
    name: str
    size: int
    last_modified: datetime


def is_configured() -> bool:
    return bool(
        os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or os.environ.get("AZURE_STORAGE_ACCOUNT")
    )


def raw_container() -> str:
    return os.environ.get("AZURE_RAW_CONTAINER", DEFAULT_RAW_CONTAINER)


def extracts_container() -> str:
    return os.environ.get("AZURE_EXTRACTS_CONTAINER", DEFAULT_EXTRACTS_CONTAINER)


def _service_client():
    from azure.storage.blob import BlobServiceClient  # lazy: only needed when Azure is used

    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    from azure.identity import DefaultAzureCredential

    account = os.environ["AZURE_STORAGE_ACCOUNT"]
    return BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )


def _container(name: str | None):
    return _service_client().get_container_client(name or raw_container())


def ensure_container(name: str | None = None) -> None:
    """Create the container if it is missing (used by tests; Terraform creates them in Azure)."""
    container = _container(name)
    if not container.exists():
        container.create_container()


def upload_file(local_path: Path, blob_name: str, container: str | None = None) -> str:
    with open(local_path, "rb") as f:
        _container(container).upload_blob(name=blob_name, data=f, overwrite=True)
    log.info("Archived %s -> azure://%s/%s", local_path, container or raw_container(), blob_name)
    return blob_name


def list_blobs(prefix: str, container: str | None = None) -> list[BlobInfo]:
    return [
        BlobInfo(name=b.name, size=b.size, last_modified=b.last_modified)
        for b in _container(container).list_blobs(name_starts_with=prefix)
    ]


def download_file(blob_name: str, dest: Path, container: str | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = _container(container).download_blob(blob_name).readall()
    dest.write_bytes(data)
    return dest


def latest_modified(prefix: str, container: str | None = None) -> datetime | None:
    blobs = list_blobs(prefix, container)
    return max((b.last_modified for b in blobs), default=None)
