"""TORY-27 guard regressions; no subprocesses or databases used by these mocks."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("backup_tool", Path(__file__).resolve().parents[1] / "scripts/tory27_backup_restore.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class BackupRestoreGuardTests(TestCase):
    def test_protected_and_non_disposable_targets_rejected(self):
        for target in ("tory", tool.BROWSER, "source", "development", "other", "x;DROP DATABASE tory"):
            with self.subTest(target=target), self.assertRaises(tool.GuardError):
                tool.target_guard(target, "source", "development")
        tool.target_guard("tory_restore_20261119_a123456789ab", "source", "development")

    def test_repository_archives_rejected(self):
        with self.assertRaises(tool.GuardError):
            tool.private_archive(tool.ROOT / "archive.dump")

    def test_subprocess_exit_propagates_without_shell_or_diagnostics(self):
        with patch.object(tool.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as run:
            with self.assertRaises(tool.ToolFailure) as rejected:
                tool.run(["pg_dump.exe", "--format=custom"], {"PGPASSWORD": "private"})
        self.assertEqual(rejected.exception.code, 7)
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertNotIn("private", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["stderr"], tool.subprocess.DEVNULL)

    def test_existing_archive_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.dump"
            path.write_bytes(b"original")
            args = SimpleNamespace(archive=str(path), source="source", pg_bin="unused")
            with patch.object(tool, "private_archive", return_value=path), patch.object(tool, "connection") as conn:
                with self.assertRaises(FileExistsError):
                    tool.backup(args, {})
                conn.assert_not_called()
            self.assertEqual(path.read_bytes(), b"original")

    def test_manifest_mismatch_blocks_database_connection(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.dump"
            path.write_bytes(b"PGDMPdummy")
            path.with_name(path.name + ".json").write_text(json.dumps({"version": 1, "source": "source", "archive_sha256": "wrong"}))
            args = SimpleNamespace(archive=str(path), source="source", target="tory_restore_20261119_a123456789ab")
            with patch.object(tool, "private_archive", return_value=path), patch.object(tool, "connection") as conn:
                with self.assertRaises(tool.GuardError):
                    tool.restore(args, {"POSTGRES_DB": "tory"})
                conn.assert_not_called()

    def test_existing_target_blocks_create_and_restore(self):
        import json
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.dump"
            path.write_bytes(b"PGDMPdummy")
            path.with_name(path.name + ".json").write_text(json.dumps({"version": 1, "source": "source", "archive_sha256": tool.digest_file(path)}))
            args = SimpleNamespace(archive=str(path), source="source", target="tory_restore_20261119_a123456789ab")
            conn = MagicMock()
            conn.execute.return_value.fetchone.return_value = (1,)
            with patch.object(tool, "private_archive", return_value=path), patch.object(tool, "connection") as connect, patch.object(tool, "run") as run:
                connect.return_value.__enter__.return_value = conn
                with self.assertRaises(tool.GuardError):
                    tool.restore(args, {"POSTGRES_DB": "tory"})
                self.assertEqual(conn.execute.call_count, 1)
                self.assertIn("SELECT 1 FROM pg_database", conn.execute.call_args.args[0])
                run.assert_not_called()

    def test_inspection_rolls_back_read_only_transaction_on_error(self):
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute.side_effect = [None, None, RuntimeError("private") , None]
        with self.assertRaises(RuntimeError):
            tool.inspect(conn)
        self.assertIn("READ ONLY", conn.execute.call_args_list[0].args[0])
        self.assertEqual(conn.execute.call_args_list[-1].args[0], "ROLLBACK")


class RestoreLifecycleTests(TestCase):
    def exercise(self, fault=None):
        import json
        from unittest.mock import MagicMock
        self.state = {"created": False, "allowed": None, "readonly": False}
        self.commands = []
        maintenance = MagicMock()
        restored = MagicMock()
        restored.execute.return_value.fetchone.return_value = ("on",)
        def execute(query, params=None):
            text = query if isinstance(query, str) else query.as_string()
            self.commands.append(text)
            cursor = MagicMock()
            if text.startswith("SELECT 1 FROM pg_database"):
                cursor.fetchone.return_value = None
            elif text.startswith("CREATE DATABASE"):
                self.assertIn('"tory_restore_20261119_a123456789ab"', text)
                self.assertIn("ALLOW_CONNECTIONS false", text)
                self.state.update(created=True, allowed=False)
            elif "SET default_transaction_read_only=on" in text:
                if fault == "interrupt":
                    raise KeyboardInterrupt()
                if fault == "configure":
                    raise tool.psycopg.OperationalError("mock failure")
                self.state["readonly"] = True
            elif text.startswith("SELECT d.datallowconn"):
                cursor.fetchone.return_value = (self.state["allowed"], self.state["readonly"])
                if fault == "verify" and not self.state["allowed"]:
                    cursor.fetchone.return_value = (False, False)
                if fault == "final_verify" and self.commands.count('ALTER DATABASE "tory_restore_20261119_a123456789ab" ALLOW_CONNECTIONS false'):
                    cursor.fetchone.return_value = (True, True)
            elif "ALLOW_CONNECTIONS true" in text:
                self.assertTrue(self.state["readonly"])
                self.assertTrue(any(t.startswith("SELECT d.datallowconn") for t in self.commands))
                self.state["allowed"] = True
            elif "ALLOW_CONNECTIONS false" in text:
                self.state["allowed"] = False
            elif text.startswith("SELECT count(*) FROM pg_stat_activity"):
                cursor.fetchone.return_value = (0,)
            else:
                self.fail("Unexpected maintenance operation")
            return cursor
        maintenance.execute.side_effect = execute
        evidence = {"pending_imports": 0, "pending_activations": 0}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.dump"
            path.write_bytes(b"PGDMPdummy")
            path.with_name(path.name + ".json").write_text(json.dumps({"version": 1, "source": "source", "archive_sha256": tool.digest_file(path), "evidence": evidence}))
            args = SimpleNamespace(archive=str(path), source="source", target="tory_restore_20261119_a123456789ab", pg_bin="unused")
            def connect(values, database):
                context = MagicMock()
                context.__enter__.return_value = maintenance if database == "postgres" else restored
                return context
            with patch.object(tool, "private_archive", return_value=path), patch.object(tool, "connection", side_effect=connect), patch.object(tool, "client_env", return_value={}), patch.object(tool, "inspect", return_value=evidence), patch.object(tool, "run") as run, patch("builtins.print") as output:
                self.run_mock = run
                self.output = output
                if fault == "restore":
                    run.side_effect = tool.ToolFailure(7)
                tool.restore(args, {"POSTGRES_DB": "tory"})
                self.assertEqual(run.call_args.args[1], {"PGOPTIONS": "-c default_transaction_read_only=off"})

    def test_interruption_after_create_leaves_connections_disabled(self):
        with self.assertRaises(KeyboardInterrupt):
            self.exercise("interrupt")
        self.assertTrue(self.state["created"])
        self.assertFalse(self.state["allowed"])
        self.run_mock.assert_not_called()

    def test_configuration_failure_never_opens_restore_access(self):
        with self.assertRaises(tool.psycopg.OperationalError):
            self.exercise("configure")
        self.assertFalse(self.state["allowed"])
        self.run_mock.assert_not_called()

    def test_verification_failure_never_opens_restore_access(self):
        with self.assertRaises(tool.GuardError):
            self.exercise("verify")
        self.assertFalse(self.state["allowed"])
        self.run_mock.assert_not_called()

    def test_restore_failure_is_not_success_and_closes_access(self):
        with self.assertRaises(tool.ToolFailure) as rejected:
            self.exercise("restore")
        self.assertEqual(rejected.exception.code, 7)
        self.assertFalse(self.state["allowed"])
        self.output.assert_not_called()

    def test_final_quarantine_failure_is_not_success(self):
        with self.assertRaises(tool.GuardError):
            self.exercise("final_verify")
        self.output.assert_not_called()

    def test_success_requires_closed_connections_and_verified_readonly(self):
        self.exercise()
        self.assertFalse(self.state["allowed"])
        self.assertTrue(self.state["readonly"])
        self.assertIn("SELECT count(*) FROM pg_stat_activity WHERE datname=%s", self.commands)


class ConstraintDiagnosticTests(TestCase):
    def test_changed_definition_strictly_fails_and_retains_real_evidence(self):
        import json
        from unittest.mock import MagicMock
        source_rows = [("example_table", "example_check", "CHECK ((units >= 0))", True)]
        target_rows = [("example_table", "example_check", "CHECK ((units > 0))", True)]
        source_conn, target_conn = MagicMock(), MagicMock()
        source_conn.execute.return_value.fetchall.return_value = source_rows
        target_conn.execute.return_value.fetchall.return_value = target_rows
        source_details, target_details = {}, {}
        expected = {"constraints": tool.collect_constraints(source_conn, source_details)}
        actual = {"constraints": tool.collect_constraints(target_conn, target_details)}
        self.assertEqual(expected["constraints"], tool.fingerprint(source_rows))
        self.assertNotEqual(expected, actual)
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "archive.dump"
            with patch.object(tool, "private_archive", side_effect=lambda p: Path(p)):
                with self.assertRaises(tool.GuardError):
                    tool.compare_evidence(archive, expected, actual, target_details)
                first = list(Path(folder).glob("*.json"))
                self.assertEqual(len(first), 1)
                payload = json.loads(first[0].read_text())
                self.assertEqual(payload["actual_evidence"], actual)
                self.assertEqual(payload["actual_details"]["constraints"][0][2], target_rows[0][2])
                with self.assertRaises(tool.GuardError):
                    tool.compare_evidence(archive, expected, actual, target_details)
                self.assertEqual(len(list(Path(folder).glob("*.json"))), 2)
                tool.compare_evidence(archive, expected, expected, source_details)
                self.assertEqual(len(list(Path(folder).glob("*.json"))), 2)


class DisposalEquivalenceTests(TestCase):
    def details(self, definition, identity=None, validated=True):
        return {"constraint_schema": "public", "constraint_columns": ["table", "name", "definition", "validated"],
                "constraints": [[*(identity or tool.DISPOSAL_IDENTITY), definition, validated], ["z_table", "other_check", "CHECK ((n > 0))", True]]}

    def evidence(self, details):
        return {"constraints": tool.fingerprint(details["constraints"]), "tables": {"x": {"count": 1}}, "pending_imports": 0}

    def compare(self, source, target, expected=None, actual=None):
        with tempfile.TemporaryDirectory() as folder, patch.object(tool, "private_archive", side_effect=lambda p: Path(p)):
            tool.compare_evidence(Path(folder)/"archive.dump", expected or self.evidence(source), actual or self.evidence(target), target, source)
            return list(Path(folder).glob("*.json"))[0].read_text()

    def test_exact_captured_pair_accepted_without_changing_raw_hashes(self):
        source=self.details(tool.DISPOSAL_SOURCE); target=self.details(tool.DISPOSAL_TARGET)
        self.assertNotEqual(self.evidence(source), self.evidence(target))
        with patch("builtins.print") as output:
            saved=self.compare(source,target)
        self.assertIn(tool.RULE, saved)
        self.assertIn(tool.RULE, str(output.call_args))

    def test_changed_definition_fields_fail_even_with_rebound_hash(self):
        source=self.details(tool.DISPOSAL_SOURCE)
        variants=[tool.DISPOSAL_TARGET.replace("Expired", "Expired2"),
                  tool.DISPOSAL_TARGET.replace("Expired", "Other",1).replace("Damaged", "Expired",1),
                  tool.DISPOSAL_TARGET.replace("Expired", "PLACEHOLDER").replace("Damaged", "Expired").replace("PLACEHOLDER", "Damaged"),
                  tool.DISPOSAL_TARGET.replace("reason_code", "other_column"),
                  tool.DISPOSAL_TARGET.replace(" = ANY", " <> ANY"),
                  tool.DISPOSAL_TARGET.replace("::text", "::varchar")]
        for definition in variants:
            with self.subTest(definition=definition), self.assertRaises(tool.GuardError):
                self.compare(source,self.details(definition))
        with self.assertRaises(tool.GuardError):
            self.compare(source,self.details(tool.DISPOSAL_TARGET,validated=False))

    def test_wrong_identity_other_constraint_and_other_evidence_fail(self):
        source=self.details(tool.DISPOSAL_SOURCE)
        for identity in [("other_table",tool.DISPOSAL_IDENTITY[1]),(tool.DISPOSAL_IDENTITY[0],"other_constraint")]:
            with self.subTest(identity=identity),self.assertRaises(tool.GuardError):
                self.compare(self.details(tool.DISPOSAL_SOURCE,identity),self.details(tool.DISPOSAL_TARGET,identity))
        target=self.details(tool.DISPOSAL_TARGET);target["constraints"][1][2]="CHECK ((n >= 0))"
        with self.assertRaises(tool.GuardError):self.compare(source,target)
        target=self.details(tool.DISPOSAL_TARGET);actual=self.evidence(target);actual["tables"]={}
        with self.assertRaises(tool.GuardError):self.compare(source,target,actual=actual)

    def test_missing_malformed_tampered_duplicate_or_wrong_schema_details_fail(self):
        import copy
        source=self.details(tool.DISPOSAL_SOURCE); target=self.details(tool.DISPOSAL_TARGET)
        bads=[None,{}, {"constraints":[]}, self.details(tool.DISPOSAL_SOURCE)]
        duplicate=copy.deepcopy(source);duplicate["constraints"].append(duplicate["constraints"][0]);bads.append(duplicate)
        schema=copy.deepcopy(source);schema["constraint_schema"]="other";bads.append(schema)
        malformed=copy.deepcopy(source);malformed["constraints"][0][3]=1;bads.append(malformed)
        bads[3]["constraints"][0][2]="tampered"
        for bad in bads:
            with self.subTest(details=bad),self.assertRaises(tool.GuardError):
                self.compare(bad,target,expected=self.evidence(source),actual=self.evidence(target))
        # Even correctly rehashed duplicate rows cannot qualify.
        with self.assertRaises(tool.GuardError):self.compare(duplicate,target)

    def test_legacy_strict_behavior_and_unbound_sidecar_fail(self):
        import json
        source=self.details(tool.DISPOSAL_SOURCE);target=self.details(tool.DISPOSAL_TARGET)
        with tempfile.TemporaryDirectory() as folder,patch.object(tool,"private_archive",side_effect=lambda p:Path(p)):
            archive=Path(folder)/"archive.dump"
            with self.assertRaises(tool.GuardError):tool.compare_evidence(archive,self.evidence(source),self.evidence(target),target)
            self.assertIsNone(tool.load_source_details(None,archive,{}))
            sidecar=Path(folder)/"source.json"
            manifest={"source":"source", "archive_sha256":"archive-hash", "evidence":self.evidence(source)}
            payload={**manifest,"details":source}
            sidecar.write_text(json.dumps(payload));self.assertEqual(tool.load_source_details(sidecar,archive,manifest),source)
            payload["archive_sha256"]="wrong";sidecar.write_text(json.dumps(payload))
            with self.assertRaises(tool.GuardError):tool.load_source_details(sidecar,archive,manifest)

    def test_duplicate_json_object_keys_fail_closed(self):
        import json
        source=self.details(tool.DISPOSAL_SOURCE)
        manifest={"source":"source","archive_sha256":"archive-hash","evidence":self.evidence(source)}
        payload={**manifest,"details":source}
        encoded=json.dumps(payload)
        variants=[encoded.replace('"details":', '"details": {}, "details":',1),
                  encoded.replace('"constraints": [', '"constraints": [], "constraints": [',1),
                  encoded.replace('"evidence":', '"evidence": {}, "evidence":',1)]
        with tempfile.TemporaryDirectory() as folder,patch.object(tool,"private_archive",side_effect=lambda p:Path(p)):
            path=Path(folder)/"source.json"
            for text in variants:
                path.write_text(text)
                with self.subTest(text=text),self.assertRaises(tool.GuardError):
                    tool.load_source_details(path,Path(folder)/"archive.dump",manifest)
