# Tory Role and Permission Matrix

**Status:** Manager-only stock adjustment is **APPROVED BR-003**. Other action permissions are proposed/TBD; the full matrix and SRS remain unapproved. See [owner decisions](OWNER_REQUIREMENTS_DECISIONS.md).

Legend: **APPROVED** applies only to the adjustment row; **PROPOSED** is a candidate permission; **TBD** needs owner direction. This matrix is not implementation evidence.

| Capability / action | Manager | Staff | Approval note |
|---|---|---|---|
| View product identity and current on-hand quantity | **PROPOSED: Allow** | **PROPOSED: Allow** | Product fields, inactive products and visibility scope TBD |
| Create product record / assign SKU | **PROPOSED: Allow** | **PROPOSED: Deny** | Product catalog import remains excluded |
| Edit product identity or deactivate product | **PROPOSED: Allow** | **PROPOSED: Deny** | Deletion/archive and behavior with movement history TBD |
| Record stock-in | **PROPOSED: Allow** | **PROPOSED: Allow** | Quantity validation and duplicate submission policy TBD |
| Record stock-out | **PROPOSED: Allow** | **PROPOSED: Allow** | BR-002 prohibits negative stock; BR-006 counts all committed stock-outs as demand. Actor permission TBD. |
| Record stock adjustment | **APPROVED: Allow** | **APPROVED: Deny** | BR-003: Manager enters physical count and reason; resulting difference recorded. |
| Import stock-transaction CSV | **PROPOSED: Allow** | **PROPOSED: Deny** | BR-004/BR-005 fix behavior, not actor permission; catalog import out of scope. |
| View supplier lead time, safety stock and reorder settings | **PROPOSED: Allow** | **PROPOSED: Read-only** | Staff access to settings needs approval |
| Create/update supplier and reorder settings | **PROPOSED: Allow** | **PROPOSED: Deny** | “Reorder settings” fields remain TBD |
| View seven-day forecast and explanation | **PROPOSED: Allow** | **PROPOSED: Allow** | Visibility and data caveats TBD |
| View reorder recommendation and explanation | **PROPOSED: Allow** | **PROPOSED: Allow** | BR-011 makes it informational; viewing permission TBD. |
| Manage user accounts, credentials or role assignments | **TBD** | **PROPOSED: Deny** | Whether in-app account administration is in scope is unresolved; do not assume Manager is a superuser |
| Change system-wide configuration or technical settings | **PROPOSED: Deny** | **PROPOSED: Deny** | Reserved for controlled deployment/owner operations unless separately approved |
| Delete movement/import history or purge records | **PROPOSED: Deny** | **PROPOSED: Deny** | Retention and correction policy TBD; destructive maintenance not part of normal workflow |
| Export inventory/history or access reports beyond forecast explanation | **TBD** | **TBD** | No export/reporting feature is in the fixed baseline |

## Proposed authorization principles

- Authenticate all users before protected product, movement, import or forecast access (**PROPOSED**; authentication mechanism TBD).
- Enforce permissions server-side on every operation; hiding a control is not authorization (**PROPOSED security requirement**).
- Deny unlisted actions by default (**PROPOSED**).
- Keep the Manager/Staff distinction meaningful, but approve each role/action cell before Design.
- Do not treat an owner-defined role name as evidence of exact permissions or stakeholder interviews.

## Owner decisions required

Approve or revise remaining action rows, decide who provisions/deactivates users, and confirm whether inventory history/export is in scope. Any separate Staff request-for-adjustment workflow is TBD and not implied by BR-003. The full matrix still needs explicit owner approval.
