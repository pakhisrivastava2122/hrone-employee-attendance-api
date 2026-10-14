# DECISIONS.md

## 1. Indexes

I use database indexes to improve query performance and maintain data integrity. A unique index on `emp_code` prevents duplicate employee records. A compound unique index on `emp_code` and `date` ensures that an employee cannot have multiple attendance records for the same date. These indexes also support employee lookups and attendance queries. I would avoid adding indexes to every field because unnecessary indexes increase storage usage and slow down write operations.

## 2. Punch-In Race

If two identical punch-in requests arrive at the same time, both requests may initially check whether an attendance record exists. The database must enforce uniqueness on the employee and attendance date so that both requests cannot create duplicate records. One request should succeed, while the other should receive an appropriate conflict response. This behavior depends on the unique index and how duplicate-key errors are handled in the application.

## 3. Leaderboard Ties

The leaderboard should use standard competition ranking. For example, if two employees share rank 1, the next employee receives rank 3. When a tie occurs at the requested limit, all employees tied at that cutoff should be returned if required by the API contract.

## 4. Department Headcount

The department summary must include eligible employees even if they have no attendance records. This requires starting from the employee collection or otherwise including employees independently of their attendance logs before combining the attendance statistics.

## 5. Scaling to 100x Data

For a dataset 100 times larger, I would review query execution plans, validate index usage, and optimize aggregation pipelines. I would also consider pagination, workload monitoring, and database capacity to keep response times reasonable.
