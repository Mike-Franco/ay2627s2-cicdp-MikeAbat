# Tory Role and Permission Matrix

**Status:** BR-021–BR-025 approve the listed role actions and assigned-inventory scope; BR-003, BR-026–BR-028, BR-037 and BR-042–BR-045 add specific account and security constraints. Unlisted actions and mechanics remain TBD; the full SRS and Requirements exit remain unapproved. See [owner decisions](OWNER_REQUIREMENTS_DECISIONS.md).

Legend: **APPROVED** applies only to the named action and conditions; **PROPOSED** is a candidate permission; **TBD** needs owner direction. This matrix is not implementation evidence.

| Capability / action | Manager | Staff | Approval note |
|---|---|---|---|
| Sign in with email/password | **APPROVED: Active account** | **APPROVED: Active account** | BR-042/BR-045; Django authentication and server-managed sessions. Session timeout TBD. |
| End own session (logout) | **PROPOSED: Allow** | **PROPOSED: Allow** | Proposed acceptance: ended session cannot access protected operations. BR-045 approves server-managed sessions but does not specify the logout workflow. |
| Request and use password reset link | **APPROVED: Time-limited, single-use** | **APPROVED: Time-limited, single-use** | BR-044; expiry duration, email delivery and rate limiting TBD. |
| View inventory and product identity/quantity | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-021/BR-022; no viewing beyond authorized assignment. Exact fields TBD. |
| View transaction history | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-024; account/product deactivation preserves attribution (BR-019/BR-026). G-09 Option A approves committed-event coverage and linked batch/source evidence, **not** additional view/export permissions. View fields/retention and separate rejected-attempt logging TBD. |
| Create product record / assign SKU | **APPROVED: Allow within authorized business scope** | **APPROVED: Deny** | BR-021; shared catalogue per business (BR-016); BR-038 permanently reserves each SKU to its original product. Catalogue-level authorization mechanics TBD. |
| Edit product identity | **APPROVED: Allow within authorized business scope** | **APPROVED: Deny** | BR-021; BR-038 bars reassigning an existing SKU to a different product. Rename/alias details TBD. |
| Deactivate product | **APPROVED: Allow within authorized business scope only when all business inventories have zero physical stock** | **APPROVED: Deny** | BR-021/BR-040; quarantined units count as physical stock. BR-019 preserves history; BR-028 bars ordinary transactions afterward. Exact resolution workflow TBD. |
| Reactivate product | **APPROVED: Allow** | **TBD** | BR-028 explicitly grants Managers reactivation; Staff permission is not decided by this rule. |
| Record ordinary stock-in | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-021/BR-022; whole-base-unit quantities (BR-020); BR-028 bars deactivated products. |
| Record ordinary stock-out | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-021/BR-022; BR-002/BR-028/BR-029/BR-033–BR-035 constrain balance, lifecycle, batch order and expiry cutoff. |
| Dispose of quarantined units | **APPROVED: Assigned inventories in own business, with reason** | **APPROVED: Deny** | BR-037; retain attributable disposal history and exclude it from demand (BR-031). G-02 Option A keeps expired physical stock until this authorised movement; G-09 Option A requires a linked Manager-attributed committed event. Reason format and transition mechanics TBD. |
| Record stock adjustment | **APPROVED: Allow** | **APPROVED: Deny** | BR-003: Manager enters physical count and reason; resulting difference recorded. |
| Assign Staff to inventory | **APPROVED: Only Manager's authorised inventories in the same business** | **TBD** | BR-027 constrains Manager assignments; Staff assignment capability is not stated. Assignment lifecycle TBD. |
| Securely invite/create Staff account by email | **APPROVED: Allow within assignment limits** | **TBD** | BR-023/BR-043; invitee sets own password and BR-027 restricts inventory assignment. Email delivery and invitation token expiry/reuse mechanics TBD. Initial Manager is provisioned during setup. |
| Deactivate Staff account | **APPROVED: Allow** | **TBD** | BR-026 revokes protected access and retains attributable history, including when an old session exists. Exact invalidation mechanics and reactivation TBD. |
| Import stock-transaction CSV | **APPROVED: Explicitly select one authorized inventory before upload** | **APPROVED: Deny** | BR-021/BR-039; every `sku,change` row applies there. BR-036 rejects expiry-tracked positive rows; BR-041 rejects exact-byte successful re-upload only in that inventory. Catalogue import excluded. |
| View supplier lead time and safety stock | **APPROVED: Authorized scope** | **APPROVED: Authorized scope** | BR-014/BR-025; only these two reorder settings in MVP. |
| Edit supplier lead time and safety stock | **APPROVED: Authorized scope** | **APPROVED: Deny** | BR-025; BR-010/BR-015 set validation. |
| View seven-day forecast and explanation | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-021/BR-022; data coverage constraints still apply. |
| View reorder alert, suggestion and explanation | **APPROVED: Assigned inventories in own business** | **APPROVED: Assigned inventories in own business** | BR-012/BR-021/BR-022; alert and suggested quantity are distinct. |
| Other user-account, credential or role administration | **TBD** | **TBD** | BR-023/BR-026/BR-027 approve only named actions; reactivation and other administration remain unresolved. Do not assume Manager is a superuser. |
| Change system-wide configuration or technical settings | **PROPOSED: Deny** | **PROPOSED: Deny** | Reserved for controlled deployment/owner operations unless separately approved |
| Delete movement/import history or purge records | **PROPOSED: Deny** | **PROPOSED: Deny** | Approved audit and attribution requirements must remain satisfiable; retention/correction policy and maintenance rights TBD. |
| Export inventory/history or access reports beyond forecast explanation | **TBD** | **TBD** | No export/reporting feature is in the fixed baseline |

## Proposed authorization principles

- Authenticate Manager and Staff with Django-based email/password sign-in; use server-managed sessions, HttpOnly cookies, HTTPS and CSRF protection (BR-042/BR-045).
- Enforce permissions server-side on every operation; hiding a control is not authorization. Authentication never grants inventory access beyond BR-022/BR-027.
- Deny unlisted actions by default (**PROPOSED**).
- Enforce Manager assignment scope against the Manager's current authorization and business boundary (BR-027); the concurrency policy remains TBD.
- Apply BR-021–BR-025 approved cells and resolve only unlisted role/action cells and mechanics before Design.
- Do not treat an owner-defined role name as evidence of exact permissions or stakeholder interviews.

## Owner decisions required

Resolve unlisted action rows, initial Manager credential setup, account reactivation, catalogue-level authorization and history-view details. BR-042–BR-045 fix email/password authentication, secure Manager Staff email invitations with invitee-set passwords, time-limited single-use reset links, server sessions, HttpOnly cookies, HTTPS and CSRF. Email delivery, invitation/reset token expiry duration, session timeout, rate limiting and free staging feasibility remain TBD. BR-024 approves authorized history viewing but does not approve export. Any separate Staff request-for-adjustment workflow is TBD and not implied by BR-003. The remaining matrix details and complete SRS still need owner disposition.
