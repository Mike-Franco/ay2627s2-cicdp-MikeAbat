# TORY-47 audit query plans

`before.txt` and `after.txt` contain PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` output for the stock-history union (50 newest entries for one product) and dashboard recent-activity union (10 newest entries for two inventories).

The plans were captured against the local development database, which had about 1,000 receipt audit rows, three demand rows and three adjustment rows. It is a small, low-selectivity dataset: almost all receipts belonged to the selected inventory/product, so PostgreSQL correctly chose sequential scans even after the indexes were added. The elapsed times varied from 2.7 to 1.4 ms for history and 4.3 to 3.0 ms for recent activity; this tiny sample is cache-sensitive and does not establish a measured speedup. The composite indexes target the selective inventory and newest-first access pattern expected as each inventory's audit history grows.

The `before.txt` plan was captured before applying the new migrations. `after.txt` was captured after migrating and running the same query shapes.
