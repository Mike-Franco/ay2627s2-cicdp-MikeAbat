# TORY-27 local backup encryption rehearsal

**Status:** Bounded local rehearsal completed 19 November 2026. This is implementation evidence only, not owner-approved policy or proof of off-host backup capability.

## Scope and tools

Source revision: `c32bd9badbeb843f69159436f2f6d930b97bd769`.

The existing successful local archive, manifest, and bound source-constraint sidecar were verified against the [backup/restore runbook](TORY-27-local-backup-restore.md) before packaging. The archive SHA256 matched the frozen runbook value; the manifest checksum and sidecar source/archive/evidence bindings also matched. No database was accessed.

The machine architecture was AMD64/64-bit. The official [age v1.3.2 release](https://github.com/FiloSottile/age/releases/tag/v1.3.2) Windows AMD64 portable ZIP was downloaded outside the repository. Its SHA256 was `f48d8f8f9ebe903ab5027ed067652f2cc1db94bc206976430133b905dcd8e8c7`, matching the expected release checksum. The extracted `age` and `age-keygen` both reported `v1.3.2` (each `--version` exit 0). An initial extraction check looked for executables at the ZIP root and exited 1; read-only inspection found the executables under `age/`, after which both version checks succeeded. No system-wide installation was made.

Working files were kept under `C:\Users\mikef\AppData\Local\Temp\tory27-age-rehearsal-6625409bc4634bed85e51f55f6cdbeb4\work`; generated identities and recipient files were kept separately under its `keys` directory. ACLs on the root and both subdirectories were verified with inheritance disabled and access limited to the current operator and SYSTEM. No key values are recorded here.

## Reproducible local procedure and results

The exact three ZIP members were the retained custom-format dump, its `.json` manifest, and its `.source.d25933d5a7b049249a21579c181ccf21.json` constraint sidecar. No wildcard or directory-content packaging was used. Both temporary identity generations and public-recipient extractions exited 0. The ZIP had exactly three unique members and passed its structural integrity check.

| Artifact or operation | Result |
|---|---|
| Source dump `tory-fresh-b489ea3cd05d.dump` | SHA256 `6e350f8fc46dee87b6cfec811fbf762e98c31fb628e2650d05a30d4567622ff2` |
| Manifest `tory-fresh-b489ea3cd05d.dump.json` | SHA256 `82594eb34fdfa803203c2a9c7eb836f1501b577036acead4b13d05870b1728ca` |
| Bound source sidecar `tory-fresh-b489ea3cd05d.dump.source.d25933d5a7b049249a21579c181ccf21.json` | SHA256 `6467a5885a2fcfbfcd950597dfcb4f3b182fddbb423c1e3cc234a54d7a89239c` |
| Three-member ZIP `bundle.zip` | SHA256 `1943511fd69d548753f4d0de4b99b4159e8972fac63b1b6c61872af9592b3cea` |
| `age` encryption | Exit 0; ciphertext SHA256 `e84e84e7bdadcd45d057fd241344720bb2ef08f423f4dce660ee7ef841c80037` |
| Valid identity decryption | Exit 0; complete ZIP SHA256 and all three member bytes/checksums matched originals |
| Wrong identity decryption | Exit 1 as expected; rejected |
| Decryption of a copy with its final ciphertext byte flipped | Exit 1 as expected; rejected |
| Original retained inputs and ciphertext after negative cases | All checksums unchanged |

The CLI was invoked through binary-safe subprocess argument lists with `shell=False`; outputs were directed to exclusively created files, and diagnostics were suppressed. The two expected negative-case partial outputs remain in the private working directory and are unusable. The rehearsal driver exited 0. No binary/plaintext content, identity, recipient value, or private key was sent to the terminal.

## Limits

This demonstrates a local age encrypt/decrypt round trip and rejection of the two tested invalid inputs for this bundle. It does not establish that a Google Drive upload/download path works, that remote storage is private or durable, that encryption keys can be recovered after device loss, or that scheduled backup, notification, retention, and restore operations work. It does not set or approve age, Google Drive, retention, RPO, RTO, or recovery policy. Application recovery readiness, off-host backup, daily automation, hosted deployment, and full NFR-008/NFR-009 acceptance remain open. The draft policy remains a proposal only.
