"""Guarded local logical archives. No Django initialization or recovery writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
BROWSER = "tory_browser_20261118_e288d59c"


class GuardError(Exception):
    pass


class ToolFailure(Exception):
    def __init__(self, code):
        self.code = code


def run(args, env, stdout=subprocess.DEVNULL):
    # Never echo libpq/client diagnostics: they can contain connection details.
    result = subprocess.run(args, env=env, stdout=stdout, stderr=subprocess.DEVNULL,
                            shell=False)
    if result.returncode:
        raise ToolFailure(result.returncode)


def settings():
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    values.update({k: v for k, v in os.environ.items() if k.startswith("POSTGRES_")})
    required = ["POSTGRES_" + k for k in ("DB", "USER", "PASSWORD", "HOST", "PORT")]
    if any(not values.get(k) for k in required):
        raise GuardError("Required local connection settings are missing.")
    if values["POSTGRES_HOST"] not in {"127.0.0.1", "localhost", "::1"}:
        raise GuardError("Only loopback PostgreSQL is supported in this increment.")
    return values


def connection(values, database):
    # libpq can route around an explicit host or inject service/startup options.
    # Reject at this entry point, including empty overrides, before any connect.
    if any(key in os.environ for key in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")):
        raise GuardError("Inherited PostgreSQL connection overrides are not permitted.")
    if values.get("POSTGRES_HOST") not in {"127.0.0.1", "localhost", "::1"}:
        raise GuardError("Only loopback PostgreSQL is supported in this increment.")
    return psycopg.connect(dbname=database, user=values["POSTGRES_USER"],
        password=values["POSTGRES_PASSWORD"], host=values["POSTGRES_HOST"],
        port=values["POSTGRES_PORT"], autocommit=True)


def client_env(values, database):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update(PGHOST=values["POSTGRES_HOST"], PGPORT=values["POSTGRES_PORT"],
               PGUSER=values["POSTGRES_USER"], PGPASSWORD=values["POSTGRES_PASSWORD"],
               PGDATABASE=database, PGCONNECT_TIMEOUT="10")
    return env


def private_archive(path):
    path = Path(path).expanduser().resolve()
    if path == ROOT or ROOT in path.parents or not path.parent.is_dir():
        raise GuardError("Archive must be in an existing private directory outside Git.")
    if os.name != "nt" and path.parent.stat().st_mode & 0o077:
        raise GuardError("Private directory must exclude group/other permissions.")
    if os.name == "nt":
        env = os.environ.copy()
        env["TORY27_PRIVATE_DIR"] = str(path.parent)
        check = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "$allowed=@([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value,'S-1-5-18'); "
            "$acl=Get-Acl -LiteralPath $env:TORY27_PRIVATE_DIR -ErrorAction Stop; "
            "foreach($rule in $acl.Access){ if($rule.AccessControlType -eq 'Allow' -and "
            "$rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -notin $allowed){exit 1} }; exit 0"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        if check.returncode:
            raise GuardError("Directory ACL must allow only the current operator and SYSTEM.")
    return path


def target_guard(target, source, development):
    if target in {source, development, "tory", BROWSER} or not re.fullmatch(
            r"tory_restore_[0-9]{8}_[0-9a-f]{12}", target):
        raise GuardError("Use a unique disposable tory_restore_YYYYMMDD_12hex target.")


def digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()


def collect_constraints(conn, diagnostics=None):
    # Keep original projection, ORDER BY and serialization: this is not normalization.
    rows = conn.execute("SELECT c.relname, conname, pg_get_constraintdef(x.oid), convalidated FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY 1,2").fetchall()
    if diagnostics is not None:
        diagnostics.update(constraint_schema="public", constraint_columns=["table", "name", "definition", "validated"], constraints=rows)
    return fingerprint(rows)


def retain_diagnostics(archive, phase, payload):
    path = private_archive(Path(archive).with_name(
        Path(archive).name + "." + phase + "." + uuid.uuid4().hex + ".json"))
    with path.open("x", encoding="utf-8") as output:
        json.dump(payload, output, default=str, indent=2)
    return path


DISPOSAL_IDENTITY = ("receiving_stockdisposal", "disposal_reason_code_valid")
DISPOSAL_SOURCE = "CHECK (((reason_code)::text = ANY ((ARRAY['Expired'::character varying, 'Damaged'::character varying, 'Other'::character varying])::text[])))"
DISPOSAL_TARGET = "CHECK (((reason_code)::text = ANY (ARRAY[('Expired'::character varying)::text, ('Damaged'::character varying)::text, ('Other'::character varying)::text])))"
RULE = "public.receiving_stockdisposal.disposal_reason_code_valid:captured-array-casts-v1"


def bound_constraint_rows(details, evidence):
    if not isinstance(details, dict) or set(details) != {"constraint_schema", "constraint_columns", "constraints"}:
        return None
    if details["constraint_schema"] != "public" or details["constraint_columns"] != ["table", "name", "definition", "validated"]:
        return None
    rows = details["constraints"]
    if not isinstance(rows, list) or not rows:
        return None
    keys = set()
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            return None
        if any(type(value) is not str for value in row[:3]) or type(row[3]) is not bool:
            return None
        key = tuple(row[:2])
        if key in keys:
            return None
        keys.add(key)
    if fingerprint(rows) != evidence.get("constraints"):
        return None
    return rows


def disposal_equivalence(expected, actual, source_details, target_details):
    if set(expected) != set(actual) or "constraints" not in expected:
        return False
    if any(expected[key] != actual[key] for key in expected if key != "constraints"):
        return False
    source = bound_constraint_rows(source_details, expected)
    target = bound_constraint_rows(target_details, actual)
    if source is None or target is None or len(source) != len(target):
        return False
    changed = []
    for left, right in zip(source, target):
        if list(left) != list(right):
            changed.append((left, right))
    return len(changed) == 1 and tuple(changed[0][0]) == (*DISPOSAL_IDENTITY, DISPOSAL_SOURCE, True) and tuple(changed[0][1]) == (*DISPOSAL_IDENTITY, DISPOSAL_TARGET, True)


def compare_evidence(archive, expected, actual, diagnostics, source_details=None):
    if actual == expected:
        return
    accepted = disposal_equivalence(expected, actual, source_details, diagnostics)
    path = retain_diagnostics(archive, "target-equivalence" if accepted else "target-mismatch", {
        "expected_evidence": expected, "actual_evidence": actual,
        "expected_details": source_details, "actual_details": diagnostics,
        "equivalence_rule": RULE if accepted else None})
    if not accepted:
        raise GuardError("Restore evidence differs; private diagnostics retained at " + str(path))
    print("Named constraint equivalence used:", RULE, "; raw hashes remain different; diagnostics:", path)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GuardError("Duplicate object key in source constraint detail.")
        result[key] = value
    return result


def load_source_details(path, archive, manifest):
    if path is None:
        return None  # Legacy manifests retain strict hash behavior.
    path = private_archive(path)
    if path.parent != archive.parent:
        raise GuardError("Source constraint detail must be in the private archive directory.")
    payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if not isinstance(payload, dict) or payload.get("source") != manifest["source"] or payload.get("archive_sha256") != manifest["archive_sha256"] or payload.get("evidence") != manifest["evidence"]:
        raise GuardError("Source constraint detail is not bound to this manifest.")
    details = payload.get("details")
    if bound_constraint_rows(details, manifest["evidence"]) is None:
        raise GuardError("Source constraint detail is missing, malformed or tampered.")
    return details


def inspect(conn, diagnostics=None):
    """Read-only evidence; row values never leave the private connection as plaintext."""
    conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    try:
        conn.execute("SET LOCAL TIME ZONE 'UTC'")
        names = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        required = {"django_migrations", "catalogue_inventoryproduct", "receiving_stockimport",
                    "receiving_observationactivation", "receiving_receiptauditevent"}
        if not required.issubset(names):
            raise GuardError("Required Tory recovery tables are missing.")
        tables = {}
        for name in names:
            rows = conn.execute(sql.SQL("SELECT row_to_json(t)::text FROM public.{} t ORDER BY row_to_json(t)::text").format(sql.Identifier(name))).fetchall()
            tables[name] = {"count": len(rows), "sha256": fingerprint(rows)}
        constraints_hash = collect_constraints(conn, diagnostics)
        triggers = conn.execute("SELECT c.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2").fetchall()
        sequences = []
        for (name,) in conn.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename"):
            row = conn.execute(sql.SQL("SELECT last_value,is_called FROM public.{}").format(sql.Identifier(name))).fetchone()
            sequences.append((name, *row))
        pending = [conn.execute("SELECT count(*) FROM receiving_stockimport WHERE commit_attribution='pending'").fetchone()[0],
                   conn.execute("SELECT count(*) FROM receiving_observationactivation WHERE state='pending'").fetchone()[0]]
        return dict(tables=tables, constraints=constraints_hash, triggers=fingerprint(triggers),
                    sequences=fingerprint(sequences), pending_imports=pending[0], pending_activations=pending[1])
    finally:
        conn.execute("ROLLBACK")


def backup(args, values):
    archive = private_archive(args.archive)
    manifest = archive.with_name(archive.name + ".json")
    # Exclusive reservations: failed artifacts are retained, never overwritten or removed.
    with archive.open("xb") as output, manifest.open("x", encoding="utf-8") as report:
        with connection(values, args.source) as conn:
            details = {}
            before = inspect(conn, details)
            run([str(Path(args.pg_bin) / "pg_dump.exe"), "--format=custom", "--no-password"],
                client_env(values, args.source), output)
            after = inspect(conn)
        if before != after:
            raise GuardError("Source changed during backup; archive is not verified. Preserve artifacts for review.")
        json.dump(dict(version=1, source=args.source, created_utc=datetime.now(timezone.utc).isoformat(),
                       archive_sha256=digest_file(archive), evidence=before), report, indent=2)
        retain_diagnostics(archive, "source", {"source": args.source, "archive_sha256": digest_file(archive), "evidence": before, "details": details})
    print("Archive captured; no restore or application readiness is established.")


def verify_target(conn, target, *, allowed):
    row = conn.execute(
        "SELECT d.datallowconn, EXISTS (SELECT 1 FROM pg_db_role_setting s "
        "WHERE s.setdatabase=d.oid AND s.setrole=0 "
        "AND 'default_transaction_read_only=on'=ANY(s.setconfig)) "
        "FROM pg_database d WHERE d.datname=%s", (target,)).fetchone()
    if row != (allowed, True):
        raise GuardError("Target connection/read-only configuration verification failed.")


def quarantine_target(conn, target):
    conn.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(target)))
    verify_target(conn, target, allowed=False)
    if conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=%s", (target,)).fetchone() != (0,):
        raise GuardError("Target still has sessions; final quarantine not established.")


def restore(args, values):
    archive = private_archive(args.archive)
    target_guard(args.target, args.source, values["POSTGRES_DB"])
    manifest = json.loads(archive.with_name(archive.name + ".json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or manifest.get("source") != args.source or manifest.get("archive_sha256") != digest_file(archive):
        raise GuardError("Archive/manifest identity or checksum mismatch.")
    source_details = load_source_details(getattr(args, "source_constraint_details", None), archive, manifest)
    with archive.open("rb") as f:
        if f.read(5) != b"PGDMP":
            raise GuardError("A custom-format PostgreSQL archive is required.")
    with connection(values, "postgres") as conn:
        if conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (args.target,)).fetchone():
            raise GuardError("Target already exists; it will not be changed.")
        conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ALLOW_CONNECTIONS false").format(sql.Identifier(args.target)))
        # A crash here leaves a non-connectable target, even before configuration.
        conn.execute(sql.SQL("ALTER DATABASE {} SET default_transaction_read_only=on").format(sql.Identifier(args.target)))
        verify_target(conn, args.target, allowed=False)
        try:
            conn.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(args.target)))
            verify_target(conn, args.target, allowed=True)
            env = client_env(values, args.target)
            env["PGOPTIONS"] = "-c default_transaction_read_only=off"
            run([str(Path(args.pg_bin) / "pg_restore.exe"), "--no-password", "--exit-on-error",
                 "--single-transaction", "--no-owner", "--no-acl", "--dbname", args.target, str(archive)], env)
            with connection(values, args.target) as restored:
                if restored.execute("SHOW default_transaction_read_only").fetchone() != ("on",):
                    raise GuardError("Target connection read-only default was not applied.")
                details = {}
                evidence = inspect(restored, details)
        finally:
            # Best effort on exceptions/interrupts, not our pre-configuration crash guard.
            # Failure here must propagate: never claim final quarantine without verification.
            quarantine_target(conn, args.target)
    compare_evidence(archive, manifest["evidence"], evidence, details, source_details)
    print("Restore data evidence accepted (strict comparison or reported named rule); target connections disabled and read-only default verified. Application readiness NOT established.")
    print("Pending imports:", evidence["pending_imports"], "pending activations:", evidence["pending_activations"])
    if evidence["pending_imports"] or evidence["pending_activations"]:
        raise GuardError("RECOVERY BLOCKER: pending source-cluster attribution. Never run finalization here.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("--source", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--target")
    parser.add_argument("--source-constraint-details", help="Explicit private source sidecar bound to this archive/manifest")
    parser.add_argument("--source-quiesced", action="store_true")
    parser.add_argument("--private-directory-confirmed", action="store_true")
    args = parser.parse_args()
    try:
        if not args.private_directory_confirmed or not args.source_quiesced:
            raise GuardError("Confirm private ACLs and quiesce source writers before operating.")
        if args.operation == "restore" and not args.target:
            raise GuardError("Restore requires an explicit disposable target.")
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", args.source):
            raise GuardError("Use a plain source database name, not a connection string.")
        values = settings()
        (backup if args.operation == "backup" else restore)(args, values)
        return 0
    except ToolFailure as error:
        print("PostgreSQL client failed; exit code", error.code, file=sys.stderr)
        return error.code if error.code > 0 else 1
    except GuardError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, psycopg.Error):
        # Do not print exception text: connection settings and row data are private.
        print("Operation failed or recovery blocked. Keep artifacts and target offline; review runbook.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
