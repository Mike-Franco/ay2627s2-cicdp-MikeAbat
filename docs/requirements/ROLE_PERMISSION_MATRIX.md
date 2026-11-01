# Tory Role and Permission Matrix

**Status:** BR-021–BR-025 approve the listed role actions and assigned-inventory scope; BR-003 and BR-026–BR-028 add specific constraints. Unlisted actions and mechanics remain TBD; the full SRS and Requirements exit remain unapproved. See [owner decisions](OWNER_REQUIREMENTS_DECISIONS.md).

Legend: **APPROVED** applies only to the named action and conditions; **PROPOSED** is a candidate permission; **TBD** needs owner direction. This matrix is not implementation evidence.

| Capability / action | Manager | Staff | Approval note |
|---|---|---|---|
| View inventory and product identity/quantity | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-021/BR-022; no viewing beyond authorized assignment. Exact fields TBD. |
| View transaction history | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-024; history survives product deactivation (BR-019). Fields/retention TBD. |
| Create product record / assign SKU | **APPROVED: Allow within authorized business scope** | **APPROVED: Deny** | BR-021; shared catalogue per business (BR-016); catalog CSV remains excluded. Catalogue-level authorization mechanics TBD. |
| Edit product identity | **APPROVED: Allow within authorized business scope** | **APPROVED: Deny** | BR-021; SKU rename/reuse and other edit details TBD. |
| Deactivate product | **APPROVED: Allow within authorized business scope** | **APPROVED: Deny** | BR-021 supplies Manager actor; BR-019 requires soft deactivation/history; BR-028 requires remaining-stock resolution and blocks ordinary transactions afterward. Exact workflow TBD. |
| Reactivate product | **APPROVED: Allow** | **TBD** | BR-028 explicitly grants Managers reactivation; Staff permission is not decided by this rule. |
| Record ordinary stock-in | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-021/BR-022; whole-base-unit quantities (BR-020); BR-028 bars deactivated products. |
| Record ordinary stock-out | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-021/BR-022; BR-002/BR-028/BR-029/BR-033 constrain balance, lifecycle and batch issue. |
| Record stock adjustment | **APPROVED: Allow** | **APPROVED: Deny** | BR-003: Manager enters physical count and reason; resulting difference recorded. |
| Assign Staff to inventory | **APPROVED: Only Manager's authorised inventories in the same business** | **TBD** | BR-027 constrains Manager assignments; Staff assignment capability is not stated. Assignment lifecycle TBD. |
| Invite/create Staff account | **APPROVED: Allow** | **TBD** | BR-023; invitation/authentication mechanics and Staff self-service rights TBD. Initial Manager is provisioned during setup. |
| Deactivate Staff account | **APPROVED: Allow** | **TBD** | BR-026 revokes access and retains attributable history; session timing and reactivation TBD. |
| Import stock-transaction CSV | **APPROVED: Assigned inventories in own business** | **APPROVED: Deny** | BR-021; BR-004/BR-005 fix batch behavior; catalogue import excluded. |
| View supplier lead time and safety stock | **APPROVED: Authorized scope** | **APPROVED: Authorized scope** | BR-014/BR-025; only these two reorder settings in MVP. |
| Edit supplier lead time and safety stock | **APPROVED: Authorized scope** | **APPROVED: Deny** | BR-025; BR-010/BR-015 set validation. |
| View seven-day forecast and explanation | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-021/BR-022; data coverage constraints still apply. |
| View reorder alert, suggestion and explanation | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-012/BR-021/BR-022; alert and suggested quantity are distinct. |
| Other user-account, credential or role administration | **TBD** | **TBD** | BR-023/BR-026/BR-027 approve only named actions; reactivation and other administration remain unresolved. Do not assume Manager is a superuser. |
| Change system-wide configuration or technical settings | **PROPOSED: Deny** | **PROPOSED: Deny** | Reserved for controlled deployment/owner operations unless separately approved |
| Delete movement/import history or purge records | **PROPOSED: Deny** | **PROPOSED: Deny** | Retention and correction policy TBD; destructive maintenance not part of normal workflow |
| Export inventory/history or access reports beyond forecast explanation | **TBD** | **TBD** | No export/reporting feature is in the fixed baseline |

## Proposed authorization principles

- Authenticate users before protected product, movement, history, import or forecast access; exact authentication mechanism TBD (BR-022/BR-023).
- Enforce permissions server-side on every operation; hiding a control is not authorization (**PROPOSED security requirement**).
- Deny unlisted actions by default (**PROPOSED**).
- Enforce Manager assignment scope against the Manager's current authorization and business boundary (BR-027); the concurrency policy remains TBD.
- Apply BR-021–BR-025 approved cells and resolve only unlisted role/action cells and mechanics before Design.
- Do not treat an owner-defined role name as evidence of exact permissions or stakeholder interviews.

## Owner decisions required

Resolve unlisted action rows, initial Manager setup and Staff invitation/authentication mechanics, account reactivation, catalogue-level authorization and history-view details. BR-023 fixes who provisions the initial Manager and who invites/creates Staff; BR-024 approves authorized history viewing but does not approve export. Any separate Staff request-for-adjustment workflow is TBD and not implied by BR-003. The remaining matrix details and complete SRS still need owner disposition.
