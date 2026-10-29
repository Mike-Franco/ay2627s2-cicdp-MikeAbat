# Tory Role and Permission Matrix

**Status:** Proposal for owner approval; only the existence of Manager and Staff roles with distinct permissions is confirmed. **Every action-level permission below is PROPOSED, not approved.**

Legend: **PROPOSED: Allow** means candidate permission; **PROPOSED: Deny** means candidate restriction; **TBD** means no recommendation is safe without owner direction. This matrix is not implementation evidence.

| Capability / action | Manager | Staff | Approval note |
|---|---|---|---|
| View product identity and current on-hand quantity | **PROPOSED: Allow** | **PROPOSED: Allow** | Product fields, inactive products and visibility scope TBD |
| Create product record / assign SKU | **PROPOSED: Allow** | **PROPOSED: Deny** | Product catalog import remains excluded |
| Edit product identity or deactivate product | **PROPOSED: Allow** | **PROPOSED: Deny** | Deletion/archive and behavior with movement history TBD |
| Record stock-in | **PROPOSED: Allow** | **PROPOSED: Allow** | Quantity validation and duplicate submission policy TBD |
| Record stock-out | **PROPOSED: Allow** | **PROPOSED: Allow** | Whether it represents demand and negative-stock policy TBD |
| Record stock adjustment | **PROPOSED: Allow** | **PROPOSED: Deny** | Adjustment representation and whether Staff can request one TBD |
| Import stock-transaction CSV | **PROPOSED: Allow** | **PROPOSED: Deny** | Manager-only reduces risk but has not been approved; product catalog import denied/out of scope for both |
| View supplier lead time, safety stock and reorder settings | **PROPOSED: Allow** | **PROPOSED: Read-only** | Staff access to settings needs approval |
| Create/update supplier and reorder settings | **PROPOSED: Allow** | **PROPOSED: Deny** | “Reorder settings” fields remain TBD |
| View seven-day forecast and explanation | **PROPOSED: Allow** | **PROPOSED: Allow** | Visibility and data caveats TBD |
| View reorder recommendation and explanation | **PROPOSED: Allow** | **PROPOSED: Allow** | Recommendation is informational; no order placement |
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

Approve or revise every action row, decide whether staff can initiate/submit adjustments, decide who provisions/deactivates users, and confirm whether inventory history/export is in scope. The matrix will be baselined only after explicit owner approval; changes after that point require SRS change control.
