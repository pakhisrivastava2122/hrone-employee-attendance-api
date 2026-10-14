# REVIEW.md

This document lists defects identified during the review of the starter `app/main.py`, how they can be detected, and the corresponding fixes.

| **#** | **Where (function / line)** | **What is wrong** | **How you'd notice it (test, input, or symptom)** | **How you fixed it** |
|---|---|---|---|---|
| 1 | `department_trend()` | The trend date-range validation allowed a range longer than the specified maximum of 92 days. | Submit a request with a date range exceeding 92 days. The API should reject it with HTTP 422. | Updated the validation to reject ranges where `(end_day - start_day).days > 91`, limiting the inclusive date range to 92 days. |
| 2 | Leaderboard endpoint | Applying `$limit` immediately after ranking can exclude employees tied at the cutoff rank. | Create multiple employees with identical total late minutes at the leaderboard limit. Verify that all employees tied at the cutoff are returned. | Adjusted the leaderboard pipeline so that ranking and limit handling preserve all employees tied at the cutoff, as required by the API contract. |
| 3 | Explain endpoint | The explain functionality did not accurately represent the actual endpoint query pipeline and its filtering, sorting, or pagination behavior. | Compare the explain output with the pipeline used by the corresponding endpoint. Differences in filters, sorting, or pagination indicate the defect. | Updated the explain functionality to reflect the actual query pipeline and relevant query options used by the endpoint. |

## Items Reviewed but Not Considered Defects

- **Unique indexes:** A unique index on `emp_code` and a compound unique index on `(emp_code, date)` are appropriate for preventing duplicate employees and duplicate daily attendance records, respectively, provided the data model and index definitions match these constraints.

- **MongoDB aggregation:** Using aggregation pipelines for analytics is appropriate because calculations can be performed in the database rather than loading large attendance collections into Python.

- **HTTP 422 for invalid input:** Returning HTTP 422 for invalid request data is appropriate when consistent with the API contract.

- **HTTP 404 for missing records:** Returning HTTP 404 when the requested employee or attendance record does not exist is appropriate when required by the API contract.

## Verification Notes

The defects listed above should be tested against the original starter implementation and the updated code. Additional defects should be documented only when supported by code inspection or reproducible tests.

The final implementation should be checked against the requirements in `openapi.yaml`, including validation, concurrency, attendance calculations, audit history, analytics correctness, and query performance.
