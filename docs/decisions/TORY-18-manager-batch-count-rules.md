# TORY-18 approved Manager batch-count rules

**Status:** Owner-approved behavior captured for TORY-18 implementation, 8 November 2026. This records the selected batch-count behavior; it does not close the wider G-05 disposition gap or approve a general design/requirements gate.

## Approved behavior

- An assigned Manager records an absolute, whole-base-unit observed count for each existing batch being corrected and supplies a mandatory reason. Zero is a valid observed batch count when it reflects the physical count.
- The Manager confirms the identity and physical count of each selected batch. For an increase, the confirmation is required to establish that the added units belong to that existing batch. Preserve the batch identity and its recorded expiry date; adjustments do not use FEFO.
- Only existing, non-expired and non-quarantined batches may be adjusted. Expiry eligibility uses the Asia/Singapore calendar date: a batch expiring today or earlier is ineligible. The adjustment never creates a batch.
- The resulting InventoryProduct physical total is calculated from the selected batches' absolute counts and their locked prior remaining quantities. Batch changes, aggregate balance and one attributable non-demand adjustment audit commit or roll back together. Adjustment evidence is separate from demand/forecast audit.
- Unmatched physical stock and missing quarantined stock remain deferred scope. Deliberate removal of quarantined units remains in BR-037 disposal and is not part of this count adjustment.

## Scope boundary

This decision does not define evidence retention, adjustment history browsing, or rejected-attempt logging. It does not resolve G-02's still-open expiry-transition evidence-recording delay, nor authorize adjustments to expired or quarantined batches.
