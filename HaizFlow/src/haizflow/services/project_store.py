"""Persistent metadata for desktop projects, including projects without jobs."""

import json
import os
import shutil
import stat
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.core.file_lock import interprocess_file_lock


PROJECT_INDEX_PATH = os.path.join(RUNTIME_DATA_DIR, "projects.json")
PROJECT_MANIFEST_NAME = ".haizflow-project.json"
PROJECT_SCHEMA_VERSION = 4
PROJECT_METADATA_TYPE = "haizflow.project"

_INDEX_LOCK = threading.RLock()
_WINDOWS_INVALID_NAME_CHARACTERS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _force_remove_readonly(func, path, _exc_info) -> None:
    """Retry a project-owned file after clearing Windows' read-only flag."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _remove_project_root(root: str, attempts: int = 8, delay_seconds: float = 0.35) -> None:
    """Remove only the validated project root, tolerating brief Windows locks."""
    last_error = None
    for attempt in range(attempts):
        try:
            shutil.rmtree(root, onerror=_force_remove_readonly)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(delay_seconds * (attempt + 1))

    if os.path.exists(root):
        raise RuntimeError(f"Could not delete project folder after {attempts} attempts: {last_error}")


def safe_project_name(project_name: str) -> str:
    """Return the legacy directory label used before UUID-backed storage."""
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_", " "} else "_"
        for character in project_name.strip()
    ).strip()
    return cleaned or "project"


def _storage_label(project_name: str) -> str:
    """Keep UUID-backed folder names readable without risking long Windows paths."""
    return safe_project_name(project_name)[:64].rstrip(" .") or "project"


def validate_new_project_name(project_name: str) -> str:
    """Validate a new display name without using it as the storage identity."""
    name = project_name.strip()
    if not name:
        raise ValueError("Enter a project name.")
    if len(name) > 120:
        raise ValueError("Project names cannot exceed 120 characters.")
    if any(ord(character) < 32 or character in _WINDOWS_INVALID_NAME_CHARACTERS for character in name):
        raise ValueError('Project names cannot contain < > : " / \\ | ? * or control characters.')
    if name.endswith((" ", ".")):
        raise ValueError("Project names cannot end with a space or period.")
    reserved_stem = name.split(".", 1)[0].upper()
    if reserved_stem in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"'{name}' is reserved by Windows. Choose another project name.")
    return name


def project_key(project_name: str, project_directory: str, project_type: str) -> str:
    """Return the legacy name-derived key used by metadata before schema v4.

    New project records must use :func:`project_identity_key`.  This helper is
    intentionally retained for migration and legacy discovery only.
    """
    directory = os.path.abspath(project_directory).lower()
    kind = "batch" if project_type == "batch" else "single"
    return f"{kind}:{directory}:{project_name.strip().lower()}"


def project_identity_key(project_id: str) -> str:
    """Return the stable identity key for one persisted project."""
    try:
        normalized_id = str(uuid.UUID(str(project_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Project metadata contains an invalid project ID.") from exc
    return f"project:{normalized_id}"


def _validate_project_root(root: str, project_directory: str) -> str:
    directory = os.path.abspath(project_directory)
    candidate = os.path.abspath(root)
    try:
        lexical_child = os.path.commonpath([directory, candidate]) == directory and candidate != directory
        resolved_directory = os.path.realpath(directory)
        resolved_candidate = os.path.realpath(candidate)
        resolved_child = (
            os.path.commonpath([resolved_directory, resolved_candidate]) == resolved_directory
            and resolved_candidate != resolved_directory
        )
    except ValueError as exc:
        raise ValueError("Project folder is outside the selected project directory.") from exc
    if not lexical_child or not resolved_child:
        raise ValueError("Project folder is outside the selected project directory.")
    return candidate


def _legacy_project_root(project_name: str, project_directory: str) -> str:
    directory = os.path.abspath(project_directory)
    return _validate_project_root(os.path.join(directory, safe_project_name(project_name)), directory)


def _record_root(record: dict[str, Any]) -> str:
    directory_value = str(record.get("project_directory") or "").strip()
    if not directory_value:
        raise ValueError("Project metadata does not contain a storage directory.")
    directory = os.path.abspath(directory_value)
    root = str(record.get("project_root") or "").strip()
    if not root:
        root = _legacy_project_root(str(record.get("project_name") or "project"), directory)
    return _validate_project_root(root, directory)


def _matching_records(
    records: list[dict[str, Any]],
    project_name: str,
    project_directory: str,
    project_type: str | None,
) -> list[dict[str, Any]]:
    directory = os.path.abspath(project_directory).lower()
    name = project_name.strip().lower()
    kind = "batch" if project_type == "batch" else "single" if project_type is not None else None
    return [
        record
        for record in records
        if os.path.abspath(str(record.get("project_directory") or "")).lower() == directory
        and str(record.get("project_name") or "").strip().lower() == name
        and (kind is None or ("batch" if record.get("project_type") == "batch" else "single") == kind)
    ]


def project_root(project_name: str, project_directory: str, project_type: str | None = None) -> str:
    """Resolve the persisted project root; never derive a new project's identity from its name."""
    directory_input = project_directory.strip()
    if not directory_input:
        raise ValueError("Choose a project folder.")
    directory = os.path.abspath(directory_input)
    with _index_guard():
        matches = _matching_records(_load_index(), project_name, directory, project_type)
    if len(matches) > 1:
        raise RuntimeError(
            "Project storage is ambiguous. Back up the project and repair its metadata before continuing."
        )
    if matches:
        return _record_root(matches[0])
    # Older installations may have a project folder but no index entry yet.
    return _legacy_project_root(project_name, directory)


def get_project(project_key_value: str) -> dict[str, Any] | None:
    """Find a project by its UUID-backed key without consulting its display name."""
    key = str(project_key_value or "").strip()
    if not key:
        return None
    with _index_guard():
        return next((record for record in _load_index() if record.get("key") == key), None)


def project_root_for_key(project_key_value: str) -> str:
    """Resolve a project root using only the immutable project key."""
    record = get_project(project_key_value)
    if not record:
        raise ValueError("The selected project no longer exists.")
    return _record_root(record)


def project_exports_dir_for_key(project_key_value: str) -> str:
    return os.path.join(project_root_for_key(project_key_value), "exports")


def project_videos_dir_for_key(project_key_value: str) -> str:
    return os.path.join(project_root_for_key(project_key_value), "videos")


def resolve_project_key(project_name: str, project_directory: str, project_type: str | None = None) -> str:
    """Resolve legacy name metadata only when it identifies exactly one project."""
    directory_input = str(project_directory or "").strip()
    if not directory_input:
        return ""
    with _index_guard():
        matches = _matching_records(_load_index(), project_name, os.path.abspath(directory_input), project_type)
    return str(matches[0].get("key") or "") if len(matches) == 1 else ""


def project_exports_dir(project_name: str, project_directory: str, project_type: str | None = None) -> str:
    """Return the dedicated export directory inside a project."""
    return os.path.join(project_root(project_name, project_directory, project_type), "exports")


def project_videos_dir(project_name: str, project_directory: str, project_type: str | None = None) -> str:
    """Return the directory that owns per-video inputs, logs, and workspace data."""
    return os.path.join(project_root(project_name, project_directory, project_type), "videos")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProjectMetadataError(RuntimeError):
    pass


class UnsupportedProjectSchemaError(ProjectMetadataError):
    pass


def _index_backup_path() -> str:
    return f"{PROJECT_INDEX_PATH}.bak"


def _index_lock_path() -> str:
    return f"{PROJECT_INDEX_PATH}.lock"


def _project_roots_path() -> str:
    return os.path.join(os.path.dirname(PROJECT_INDEX_PATH), "project-roots.json")


@contextmanager
def _index_guard():
    with _INDEX_LOCK:
        with interprocess_file_lock(_index_lock_path()):
            yield


def _write_json_atomic(path: str, data: Any) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary_path = tempfile.mkstemp(prefix=".projects-", suffix=".json.tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.remove(temporary_path)
        except FileNotFoundError:
            pass
        raise


def _schema_version(data: dict[str, Any], *, label: str) -> int:
    raw_version = data.get("schema_version", 1)
    try:
        version = int(raw_version)
    except (TypeError, ValueError) as exc:
        raise ProjectMetadataError(f"{label} has an invalid schema version: {raw_version!r}") from exc
    if version < 1:
        raise ProjectMetadataError(f"{label} has an invalid schema version: {version}")
    if version > PROJECT_SCHEMA_VERSION:
        raise UnsupportedProjectSchemaError(
            f"{label} uses schema v{version}, newer than supported v{PROJECT_SCHEMA_VERSION}."
        )
    return version


def _migrate_project_record(raw_record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if not isinstance(raw_record, dict):
        raise ProjectMetadataError("Project index contains a non-object record.")
    original = dict(raw_record)
    record = dict(raw_record)
    version = _schema_version(record, label="Project metadata")

    while version < PROJECT_SCHEMA_VERSION:
        if version == 1:
            name = str(record.get("project_name") or "").strip()
            directory_value = str(record.get("project_directory") or "").strip()
            if not name or not directory_value:
                raise ProjectMetadataError("Legacy project metadata is missing its name or directory.")
            directory = os.path.abspath(directory_value)
            kind = "batch" if record.get("project_type") == "batch" else "single"
            key = project_key(name, directory, kind)
            root = str(record.get("project_root") or _legacy_project_root(name, directory))
            record.update(
                {
                    "schema_version": 2,
                    "project_id": str(record.get("project_id") or uuid.uuid5(uuid.NAMESPACE_URL, f"haizflow:{key}")),
                    "key": key,
                    "project_name": name,
                    "project_directory": directory,
                    "project_root": _validate_project_root(root, directory),
                    "storage_name": str(record.get("storage_name") or os.path.basename(root)),
                    "storage_layout": str(record.get("storage_layout") or "legacy"),
                    "project_type": kind,
                    "created_at": str(record.get("created_at") or record.get("updated_at") or _now()),
                    "updated_at": str(record.get("updated_at") or record.get("created_at") or _now()),
                }
            )
            version = 2
            continue
        if version == 2:
            record["schema_version"] = 3
            record["metadata_type"] = PROJECT_METADATA_TYPE
            version = 3
            continue
        if version == 3:
            name = str(record.get("project_name") or "").strip()
            directory_value = str(record.get("project_directory") or "").strip()
            kind = "batch" if record.get("project_type") == "batch" else "single"
            legacy_key = project_key(name, os.path.abspath(directory_value), kind)
            project_id = str(record.get("project_id") or uuid.uuid5(uuid.NAMESPACE_URL, f"haizflow:{legacy_key}"))
            record["schema_version"] = 4
            record["project_id"] = project_id
            record["key"] = project_identity_key(project_id)
            version = 4
            continue
        raise ProjectMetadataError(f"No project migration is available from schema v{version}.")

    name = str(record.get("project_name") or "").strip()
    directory_value = str(record.get("project_directory") or "").strip()
    if not name or not directory_value:
        raise ProjectMetadataError("Project metadata is missing its name or directory.")
    directory = os.path.abspath(directory_value)
    kind = "batch" if record.get("project_type") == "batch" else "single"
    legacy_key = project_key(name, directory, kind)
    project_id = str(record.get("project_id") or uuid.uuid5(uuid.NAMESPACE_URL, f"haizflow:{legacy_key}"))
    key = project_identity_key(project_id)
    root = _record_root({**record, "project_directory": directory, "project_name": name})
    record.update(
        {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "metadata_type": PROJECT_METADATA_TYPE,
            "project_id": project_id,
            "key": key,
            "project_name": name,
            "project_directory": directory,
            "project_root": root,
            "storage_name": str(record.get("storage_name") or os.path.basename(root)),
            "storage_layout": str(record.get("storage_layout") or "legacy"),
            "project_type": kind,
            "created_at": str(record.get("created_at") or record.get("updated_at") or _now()),
            "updated_at": str(record.get("updated_at") or record.get("created_at") or _now()),
        }
    )
    return record, record != original


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _read_index_file(path: str) -> tuple[list[dict[str, Any]], bool, list[Any]]:
    raw_records = _read_json(path)
    if not isinstance(raw_records, list):
        raise ProjectMetadataError(f"Project index must contain a JSON array: {path}")
    records: list[dict[str, Any]] = []
    changed = False
    for raw_record in raw_records:
        record, migrated = _migrate_project_record(raw_record)
        records.append(record)
        changed = changed or migrated
    return records, changed, raw_records


def _write_migration_backup(path: str, data: Any) -> None:
    backup_path = f"{path}.schema-migration.bak"
    if not os.path.exists(backup_path):
        _write_json_atomic(backup_path, data)


def _remember_project_directories(records: list[dict[str, Any]]) -> None:
    registry_path = _project_roots_path()
    directories: set[str] = set()
    try:
        saved = _read_json(registry_path)
        if isinstance(saved, list):
            directories.update(os.path.abspath(str(item)) for item in saved if str(item).strip())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    directories.update(
        os.path.abspath(str(record["project_directory"]))
        for record in records
        if str(record.get("project_directory") or "").strip()
    )
    try:
        _write_json_atomic(registry_path, sorted(directories, key=str.lower))
    except OSError:
        pass


def _save_index(records: list[dict[str, Any]], *, backup_existing: bool = True) -> None:
    normalized = [_migrate_project_record(record)[0] for record in records]
    if backup_existing and os.path.isfile(PROJECT_INDEX_PATH):
        try:
            current_records, _changed, _raw = _read_index_file(PROJECT_INDEX_PATH)
            _write_json_atomic(_index_backup_path(), current_records)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProjectMetadataError):
            # Never replace the recovery backup with a damaged primary index.
            pass
    _write_json_atomic(PROJECT_INDEX_PATH, normalized)
    _remember_project_directories(normalized)


def _quarantine_corrupt_index() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    quarantine_path = f"{PROJECT_INDEX_PATH}.corrupt-{timestamp}-{os.getpid()}"
    try:
        shutil.copy2(PROJECT_INDEX_PATH, quarantine_path)
    except OSError as exc:
        raise ProjectMetadataError(
            "Project index is unreadable and could not be quarantined. No metadata was overwritten."
        ) from exc
    return quarantine_path


def _known_project_directories() -> list[str]:
    directories = {os.path.join(os.path.dirname(PROJECT_INDEX_PATH), "projects")}
    try:
        saved = _read_json(_project_roots_path())
        if isinstance(saved, list):
            directories.update(os.path.abspath(str(item)) for item in saved if str(item).strip())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return sorted(directories, key=str.lower)


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    raw = _read_json(str(manifest_path))
    record, migrated = _migrate_project_record(raw)
    expected_root = os.path.realpath(manifest_path.parent)
    if os.path.normcase(os.path.realpath(_record_root(record))) != os.path.normcase(expected_root):
        raise ProjectMetadataError(f"Project manifest root does not match its folder: {manifest_path}")
    if migrated:
        _write_migration_backup(str(manifest_path), raw)
        _write_json_atomic(str(manifest_path), record)
    return record


def _rebuild_index_from_manifests() -> list[dict[str, Any]]:
    records_by_key: dict[str, dict[str, Any]] = {}
    roots_by_key: dict[str, str] = {}
    for directory_value in _known_project_directories():
        directory = Path(directory_value)
        if not directory.is_dir():
            continue
        try:
            children = tuple(directory.iterdir())
        except OSError:
            continue
        for child in children:
            manifest_path = child / PROJECT_MANIFEST_NAME
            if not child.is_dir() or not manifest_path.is_file():
                continue
            try:
                record = _load_manifest(manifest_path)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProjectMetadataError):
                continue
            key = record["key"]
            root = os.path.normcase(_record_root(record))
            if key in records_by_key or root in roots_by_key.values():
                continue
            records_by_key[key] = record
            roots_by_key[key] = root
    return list(records_by_key.values())


def _merge_recovered_records(
    recovered: list[dict[str, Any]], manifests: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records_by_key = {record["key"]: record for record in recovered}
    roots_by_key = {key: os.path.normcase(_record_root(record)) for key, record in records_by_key.items()}
    for record in manifests:
        key = record["key"]
        root = os.path.normcase(_record_root(record))
        conflicting_key = next((item_key for item_key, item_root in roots_by_key.items() if item_root == root), None)
        if conflicting_key is not None and conflicting_key != key:
            continue
        records_by_key[key] = record
        roots_by_key[key] = root
    return list(records_by_key.values())


def _migrate_registered_manifests(records: list[dict[str, Any]]) -> None:
    for record in records:
        try:
            manifest_path = Path(_record_root(record)) / PROJECT_MANIFEST_NAME
            if manifest_path.is_file():
                _load_manifest(manifest_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProjectMetadataError):
            continue


def _load_index() -> list[dict[str, Any]]:
    primary_existed = os.path.exists(PROJECT_INDEX_PATH)
    if primary_existed:
        try:
            records, migrated, raw_records = _read_index_file(PROJECT_INDEX_PATH)
            if migrated:
                _write_migration_backup(PROJECT_INDEX_PATH, raw_records)
                _save_index(records)
            else:
                _remember_project_directories(records)
            _migrate_registered_manifests(records)
            return records
        except UnsupportedProjectSchemaError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProjectMetadataError):
            _quarantine_corrupt_index()

    backup_path = _index_backup_path()
    if os.path.isfile(backup_path):
        try:
            records, _migrated, _raw_records = _read_index_file(backup_path)
            records = _merge_recovered_records(records, _rebuild_index_from_manifests())
            _save_index(records, backup_existing=False)
            _migrate_registered_manifests(records)
            return records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProjectMetadataError):
            pass

    rebuilt = _rebuild_index_from_manifests()
    if rebuilt:
        _save_index(rebuilt, backup_existing=False)
        _migrate_registered_manifests(rebuilt)
        return rebuilt
    if primary_existed:
        raise ProjectMetadataError(
            "Project index was damaged and no valid backup or project manifest could rebuild it. "
            "The damaged index was quarantined and no empty index was written."
        )
    return []


def _write_project_record(records: list[dict[str, Any]], record: dict[str, Any]) -> dict[str, Any]:
    """Persist one already-normalized record and its owned directory layout."""
    root = _record_root(record)
    os.makedirs(root, exist_ok=True)
    os.makedirs(os.path.join(root, "exports"), exist_ok=True)
    os.makedirs(os.path.join(root, "videos"), exist_ok=True)
    _write_json_atomic(os.path.join(root, PROJECT_MANIFEST_NAME), record)
    records = [item for item in records if item.get("key") != record["key"]]
    records.append(record)
    _save_index(records)
    return record


def create_project(project_name: str, project_directory: str, project_type: str) -> dict[str, Any]:
    """Create a distinct project, even when its display name is already used.

    The name is presentation only.  The UUID and its `project:<uuid>` key own
    the manifest, inputs, exports, and all later project operations.
    """
    name = project_name.strip()
    directory_input = project_directory.strip()
    if not directory_input:
        raise ValueError("Choose a project folder.")
    name = validate_new_project_name(name)
    directory = os.path.abspath(directory_input)
    kind = "batch" if project_type == "batch" else "single"
    now = _now()

    with _index_guard():
        records = _load_index()
        while True:
            project_id = str(uuid.uuid4())
            key = project_identity_key(project_id)
            storage_name = f"{_storage_label(name)}--{project_id}"
            root = _validate_project_root(os.path.join(directory, storage_name), directory)
            if not os.path.exists(root) and not any(item.get("key") == key for item in records):
                break

        record = {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "metadata_type": PROJECT_METADATA_TYPE,
            "project_id": project_id,
            "key": key,
            "project_name": name,
            "project_directory": directory,
            "project_root": root,
            "storage_name": storage_name,
            "storage_layout": "uuid",
            "project_type": kind,
            "created_at": now,
            "updated_at": now,
        }
        return _write_project_record(records, record)


def ensure_project(
    project_name: str,
    project_directory: str,
    project_type: str,
    *,
    project_key_value: str = "",
) -> dict[str, Any]:
    """Resolve an existing project or create one for legacy callers.

    New UI flows must call :func:`create_project`.  This compatibility method
    accepts an immutable key whenever one is known; without it, it can only
    resolve a unique legacy name/type/directory tuple.
    """
    key = str(project_key_value or "").strip()
    if key:
        with _index_guard():
            records = _load_index()
            existing = next((record for record in records if record.get("key") == key), None)
            if not existing:
                raise ValueError("The selected project no longer exists.")
            existing["updated_at"] = _now()
            return _write_project_record(records, existing)

    directory_input = project_directory.strip()
    if not directory_input:
        raise ValueError("Choose a project folder.")
    with _index_guard():
        matches = _matching_records(
            _load_index(),
            project_name,
            os.path.abspath(directory_input),
            project_type,
        )
        if len(matches) == 1:
            existing = matches[0]
            existing["updated_at"] = _now()
            return _write_project_record(_load_index(), existing)
        if len(matches) > 1:
            raise RuntimeError("Multiple projects share this name. Select the project from the project list.")
    return create_project(project_name, project_directory, project_type)


def list_projects() -> list[dict[str, Any]]:
    """Return registered projects, including projects without imported videos."""
    with _index_guard():
        records = _load_index()
    valid = [record for record in records if record.get("key") and record.get("project_name")]
    return sorted(valid, key=lambda record: record.get("updated_at", ""), reverse=True)


def _validated_deletion_record(records: list[dict[str, Any]], key: str) -> tuple[dict[str, Any], str] | None:
    record = next((item for item in records if item.get("key") == key), None)
    if not record:
        return None
    root = _record_root(record)
    duplicate_owners = [
        item
        for item in records
        if item.get("key") != key and os.path.normcase(_record_root(item)) == os.path.normcase(root)
    ]
    if duplicate_owners:
        raise RuntimeError("Deletion was blocked because another project references the same folder.")

    manifest_path = os.path.join(root, PROJECT_MANIFEST_NAME)
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as file:
                manifest = json.load(file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Deletion was blocked because the project manifest is unreadable.") from exc
        if manifest.get("key") != key:
            raise RuntimeError("Deletion was blocked because the project manifest belongs to another project.")
    elif int(record.get("schema_version") or 1) >= PROJECT_SCHEMA_VERSION:
        raise RuntimeError("Deletion was blocked because the project manifest is missing.")
    elif os.path.normcase(root) != os.path.normcase(
        _legacy_project_root(str(record.get("project_name") or "project"), str(record.get("project_directory") or ""))
    ):
        raise RuntimeError("Deletion was blocked because legacy project ownership could not be verified.")
    return record, root


def validate_project_deletion(project_name: str, project_directory: str, project_type: str) -> bool:
    """Preflight project ownership before callers stop work or remove child data."""
    key = resolve_project_key(project_name, project_directory, project_type)
    if not key:
        return False
    return validate_project_deletion_by_key(key)


def validate_project_deletion_by_key(project_key_value: str) -> bool:
    """Preflight deletion using the immutable project identity."""
    key = str(project_key_value or "").strip()
    with _index_guard():
        return _validated_deletion_record(_load_index(), key) is not None


def delete_project(project_name: str, project_directory: str, project_type: str) -> bool:
    """Remove a registered project and its project-owned output directory."""
    key = resolve_project_key(project_name, project_directory, project_type)
    if not key:
        return False
    return delete_project_by_key(key)


def delete_project_by_key(project_key_value: str) -> bool:
    """Remove exactly one project and all data it owns."""
    key = str(project_key_value or "").strip()
    with _index_guard():
        records = _load_index()
        validated = _validated_deletion_record(records, key)
        if not validated:
            return False
        _record, root = validated

        if os.path.isdir(root):
            _remove_project_root(root)
        _save_index([item for item in records if item.get("key") != key])
        return True
