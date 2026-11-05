# Tory Authorization, Catalogue and Receiving ERD

**Scope:** Implemented TORY-10, TORY-12, TORY-13 and TORY-16 structures. Stock-out, expiry transition, disposal, CSV and forecasting entities remain future work; this is not the complete Tory data model or approval of the SRS/Design gate.

## Implemented entities

```mermaid
erDiagram
    USER ||--o{ BUSINESS_MEMBERSHIP : has_membership
    BUSINESS ||--o{ BUSINESS_MEMBERSHIP : has_members
    BUSINESS ||--o{ INVENTORY : owns
    BUSINESS ||--o{ PRODUCT : catalogues
    BUSINESS_MEMBERSHIP ||--o{ INVENTORY_ASSIGNMENT : receives
    INVENTORY ||--o{ INVENTORY_ASSIGNMENT : has_assignments
    PRODUCT ||--o{ INVENTORY_PRODUCT : linked_to
    INVENTORY ||--o{ INVENTORY_PRODUCT : lists
    USER ||--o{ RECEIVING_BATCH : records
    PRODUCT ||--o{ RECEIVING_BATCH : received_as
    INVENTORY ||--o{ RECEIVING_BATCH : receives
    INVENTORY_PRODUCT ||--o{ RECEIVING_BATCH : orders
    RECEIVING_BATCH ||--|| RECEIPT_AUDIT_EVENT : evidenced_by
    USER ||--o{ RECEIPT_AUDIT_EVENT : attributed_to
    BUSINESS ||--o{ RECEIPT_AUDIT_EVENT : scopes
    INVENTORY ||--o{ RECEIPT_AUDIT_EVENT : scopes
    PRODUCT ||--o{ RECEIPT_AUDIT_EVENT : scopes

    USER {
        bigint id PK
        varchar email UK
        boolean is_active
    }
    BUSINESS {
        bigint id PK
        varchar name
        datetime created_at
    }
    BUSINESS_MEMBERSHIP {
        bigint id PK
        bigint business_id FK
        bigint user_id FK
        varchar role
        boolean is_active
    }
    INVENTORY {
        bigint id PK
        bigint business_id FK
        varchar name
        boolean is_active
        datetime created_at
    }
    INVENTORY_ASSIGNMENT {
        bigint id PK
        bigint membership_id FK
        bigint inventory_id FK
        boolean is_active
        datetime assigned_at
    }
    PRODUCT {
        bigint id PK
        bigint business_id FK
        varchar sku
        text name
        varchar base_unit_label "nullable until configured"
        boolean expiry_tracking_required "nullable until configured"
        boolean is_active
        integer lead_time_days
        integer safety_stock_units
    }
    INVENTORY_PRODUCT {
        bigint id PK
        bigint inventory_id FK
        bigint product_id FK
        decimal selling_price
        bigint physical_quantity_units
        bigint last_receipt_sequence
    }
    RECEIVING_BATCH {
        uuid id PK
        bigint actor_id FK
        bigint inventory_id FK
        bigint product_id FK
        bigint inventory_product_id FK
        varchar source
        uuid request_token
        varchar input_fingerprint
        integer quantity_units
        integer remaining_quantity_units
        integer quarantined_quantity_units
        varchar unit_label_snapshot
        date expiry_date
        bigint receipt_sequence
        datetime received_at
    }
    RECEIPT_AUDIT_EVENT {
        bigint id PK
        uuid batch_id FK_UK
        bigint actor_id FK
        bigint business_id FK
        bigint inventory_id FK
        bigint product_id FK
        varchar source
        varchar action
        varchar classification
        bigint quantity_before_units
        integer quantity_change_units
        bigint quantity_after_units
        datetime occurred_at
    }
```

The diagram matches [accounts.User](../../accounts/models.py), [inventory access models](../../inventory_access/models.py), [catalogue models](../../catalogue/models.py), [receiving models](../../receiving/models.py), and migrations through `catalogue/0005` and `receiving/0005`. Product active and receiving configuration fields were added in TORY-16; legacy Products migrate as active but with base unit and expiry policy unset. No default label or expiry policy is inferred.

## Keys, constraints and integrity

- Existing `(business_id,user_id)` membership and `(membership_id,inventory_id)` assignment uniqueness, user email uniqueness, business-scoped case-insensitive SKU uniqueness and `(inventory_id,product_id)` link uniqueness are unchanged.
- InventoryProduct now stores the physical product/inventory balance (including any future quarantined units) and last committed receipt sequence. Database checks cap the physical balance at 2,147,483,647. Direct ORM/SQL changes to those counters are rejected; inserting a valid batch through the database trigger increments them atomically.
- InventoryProduct parent identity cannot be reassigned. Its association can only be deleted while it has neither physical units nor receipt history; foreign keys and a trigger retain links referenced by a batch.
- Product requires an explicit nonblank base-unit label and non-null `expiry_tracking_required` before receipt. `is_active` defaults true, preserving existing product behavior. A receiving batch snapshots the unit label so later presentation does not alter receipt evidence.
- ReceivingBatch has a stable UUID identity, source, actor, operation-scoped request token, canonical-input SHA-256 fingerprint, whole-unit quantity, expiry, timestamp and sequence. PostgreSQL enforces token uniqueness per `(actor,source,request_token)`, unique `(inventory_product,receipt_sequence)`, positive bounded quantity, and remaining/quarantine bounds. The insert trigger checks active account/membership/assignment/inventory/product, same-business linked association, expiry policy and the aggregate balance; it advances the balance and sequence in the same transaction.
- ReceiptAuditEvent is one-to-one with a batch. Its database trigger verifies scope, actor, source, batch quantity, non-demand classification and the after-balance against the InventoryProduct aggregate. Checks bound the before/change/after quantities. A deferred constraint trigger rejects commit unless every inserted batch has its event. Update/delete triggers and protected foreign keys prevent erasing or rewriting committed receipt identity and attribution.
- The request token and batch are one row: validation or audit failure rolls the token back with the batch, balance and sequence. A replay first rechecks current authorization and matching product/link state. A committed replay compares the canonical input fingerprint before checking the current date, so an original receipt remains replayable after its expiry date passes.

## Lock protocol and authorization

Receipt transactions lock active User, BusinessMembership and InventoryAssignment rows `FOR SHARE`, then Product, Inventory and InventoryProduct `FOR UPDATE`, in that order. Shared authorization locks allow independent receipts to proceed while conflicting account/membership/assignment revocation waits. If revocation commits first, the subsequent locked read rejects; if the receipt obtains the authorization locks first, revocation waits until receipt commit. Product is the cross-inventory serialization anchor; Inventory follows Product to align with the InventoryProduct trigger.

TORY-13's former Inventory→Product trigger order was replaced in the reversible `catalogue/0004` migration with Product→Inventory. The receiving insert trigger follows the same parent order. Since an UPDATE locks InventoryProduct before its BEFORE trigger, `receiving/0004` rejects association identity changes instead of risking a link-row→parent-lock cycle against Product→Inventory→link receipt writers. InventoryProduct row locking and its database trigger serialize aggregate updates and sequence allocation. The Product lock serializes same-product receipts across inventories; the association row protects each per-inventory aggregate. Both are held through audit commit/rollback.

These locks protect only compliant receipt/balance operations and the checked scope rows. They do not implement future stock-out allocation, expiry transitions, disposal, deactivation, CSV import or forecast consistency. Those writers must share/review the lock protocol and maintain audit evidence before they are implemented. Deadlocks and serialization failures are not silently retried; a new attempt must submit the same token and pass current authorization again.

Authorization remains server-side. `receiving.services._lock_authorized_scope` rechecks active account, same-business active membership, explicit active assignment, active inventory/product and linked InventoryProduct inside the transaction. Protected views also use TORY-10 `protected_view`; forms are POST + CSRF; form IDs are never treated as authority. Manager role alone grants no inventory-wide or cross-business access.

## Provisional and unresolved details

- `base_unit_label` is stored in a 40-character field and validated as nonblank; 40 is a technical storage limit, not a separately approved label-length rule. Packaging conversion remains deferred.
- InventoryProduct's physical balance is initialized to zero on migration. There were no prior stock quantities in TORY-13 to migrate; no historical balance is fabricated.
- The operator-only `configure_receiving` command initializes a product's label and expiry policy before first receipt. There is no catalogue configuration UI or new Manager catalogue authority.
- `remaining_quantity_units` begins equal to receipt quantity and `quarantined_quantity_units` begins at zero. TORY-16 does not change them after receipt. The immutable batch trigger must be deliberately revised alongside future movement/audit logic before stock-out, expiry transition or disposal work.
- The `source` field currently permits the declared manual/CSV values in model state, but the TORY-16 database insert trigger accepts manual source only. CSV behavior and its use of the same committed ordering remain future work under G-03/G-04.
- G-02 expiry-boundary evidence delay, G-05 damaged/returned-stock disposition and disposal reason format, G-09 rejected-attempt logging, G-11 broader concurrency, G-13 lifecycle/authority and G-10 hosting feasibility remain open as recorded. Receipt audit is implemented; no other history feature is claimed.

## Future entities (not implemented)

Stock-out movements and allocation rows, expiry transition evidence, disposal/count-adjustment events, CSV import batches, demand-observation coverage, forecasts and reorder results remain future work. Their relationships must extend this ERD when implemented; the current batch's remaining/quarantined columns are not evidence that those workflows exist.
