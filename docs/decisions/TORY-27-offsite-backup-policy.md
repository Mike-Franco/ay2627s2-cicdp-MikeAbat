# TORY-27 off-site backup policy - draft

**Status:** DRAFT - proposals only; none of the policy choices below is owner-approved or a verified capability. This document does not change the approved SRS or deployment decisions.

## Approved requirement and current evidence

NFR-008 remains owner-approved as recorded in the [SRS](../requirements/SOFTWARE_REQUIREMENTS_SPECIFICATION.md): take daily PostgreSQL backups and complete at least one successful restore test before Deployment. The backup destination, retention, RPO and RTO remain undecided. The [deployment feasibility record](../requirements/DEPLOYMENT_FEASIBILITY_GAP_OWNER_DECISIONS.md) selects no provider and identifies off-site protection, automation and operating evidence as open gaps.

PR #52 added guarded local PostgreSQL backup/restore tooling and an operator runbook. The [runbook](TORY-27-local-backup-restore.md) records a successful isolated local rehearsal under the narrowly bounded `captured-array-casts-v1` constraint-equivalence rule. The raw constraint hashes were unequal, and an earlier failed rehearsal remains recorded as FAIL. A later connection-isolation correction has separate mocked-test and hosted-CI evidence; it is not a new live rehearsal. Local restore evidence does not establish off-site delivery, daily execution, or readiness to resume application service. A separate [local age encryption rehearsal](TORY-27-local-encryption-rehearsal.md) measured a local encrypt/decrypt round trip for one exact three-file bundle, including wrong-identity and corrupted-ciphertext rejection. This verifies only the exercised local cryptographic path; it does not verify off-host delivery, durable key storage or recovery, or an operating policy. The use of age in that rehearsal is not an approved tool or policy decision.

## Proposals for owner review

The following options are proposals to discuss, not approved policy or demonstrated Google Drive capabilities:

- Store client-side encrypted backup copies off-host in an existing private Google Drive.
- Retain seven successful daily copies.
- Set a proposed recovery point objective (RPO) of no more than 24 hours of data loss.
- Set a proposed recovery time objective (RTO) to restore within 24 hours after a recovery incident.

No account access, available capacity, upload/download path, encryption workflow, scheduler, alerting, retention automation, or recovery-time measurement has been verified. This proposal does not authorize account provisioning, uploads, scheduled jobs, or use of a provider feature.

## Decisions and evidence still required

Before these proposals can become an operational policy or support NFR-008 acceptance, resolve and verify:

1. **Account capacity and access:** available storage, sharing/access controls, account eligibility and no-charge safeguards.
2. **Encryption and key recovery:** client-side encryption method, key custody, authorized recovery, and a tested decrypt path independent of the backup destination.
3. **Scheduler and quiescence:** safe daily invocation, source quiescence, missed-run handling, and evidence that each scheduled copy is complete and usable.
4. **Failure notification:** detection, owner/operator notification, and escalation when backup, upload, integrity check, or retention handling fails.
5. **Retention handling:** how seven successful daily copies are counted, protected, verified, and expired without deleting the only known-good recovery point.
6. **Off-host recovery:** controlled download, checksum verification, decrypt, isolated restore, and recorded result without exposing credentials or archive contents.
7. **Pending-attribution disposition:** review unresolved StockImport/ObservationActivation origin attribution as a recovery blocker. Never infer it using destination-cluster commit timestamps or invent timestamps.
8. **Application recovery readiness:** separately verify migrations, secrets, email, schedulers, access controls, monitoring, and safe application resumption after a restored database is reviewed.

Daily automation, off-host backup, hosted deployment, and complete NFR-008/NFR-009 acceptance remain open. No owner approval is recorded here.
