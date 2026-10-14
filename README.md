# Employee Attendance & Analytics API

## Project Overview

This project implements an Employee Attendance and Analytics API using Python, FastAPI, and MongoDB.

The API manages employee attendance records, punch-in and punch-out operations, manual attendance corrections, audit history, and attendance analytics.

The implementation is expected to follow the requirements defined in `openapi.yaml` and the problem statement, including attendance calculations, validation, concurrency handling, and MongoDB aggregation.

## Technology Stack

- Python
- FastAPI
- MongoDB
- PyMongo
- Uvicorn
- MongoDB Aggregation Pipeline

## Project Structure

```text
candidate_kit/
├── app/
│   └── main.py
├── sample_data/
├── sample_seed.py
├── requirements.txt
├── openapi.yaml
├── DATA_MODEL.md
├── REVIEW.md
├── DECISIONS.md
├── README.md
└── .gitignore
```

`PROBLEM_STATEMENT.docx` contains the original assignment instructions. It is not required to be included in the public repository.

## Assignment Requirements

The implementation is based on the API contract and business rules R1–R10 defined in `openapi.yaml`.

The main requirements include:

### 1. Employee and Attendance Management

- Store employee details and attendance records in MongoDB.
- Enforce employee and attendance record uniqueness using appropriate database constraints and indexes.
- Support attendance records associated with employees and dates.

### 2. Punch-In and Punch-Out

- Validate punch-in and punch-out requests.
- Calculate late minutes, work hours, overtime, and half-day status according to the specified business rules.
- Handle invalid requests and duplicate or concurrent operations appropriately.
- Reject invalid timestamps and punch-out times that violate the defined rules.

### 3. Attendance Listing and Corrections

- Retrieve attendance records with the required filters and sorting.
- Support manual attendance corrections.
- Recalculate derived attendance fields after valid corrections.
- Maintain an audit trail of actual changes.
- Validate attendance status and punch-time combinations.
- Handle missing records, invalid updates, and concurrent modifications appropriately.

### 4. Employee Monthly Analytics

- Calculate monthly attendance statistics for an employee.
- Include working days, present days, leave days, late counts, and attendance percentage.
- Follow the specified rules for half-days and months with no working days.

### 5. Department Summary

- Provide monthly attendance summaries for departments.
- Include employee headcount, attendance statistics, late minutes, leave counts, and on-duty counts as required.
- Include eligible employees even when they have no attendance logs.
- Support department filtering where specified.

### 6. Late-Minute Leaderboard

- Rank employees by total late minutes for the requested period.
- Use standard competition ranking for ties.
- Include employees tied at the cutoff when required by the API contract.
- Calculate attendance rates and seven-day moving averages according to the specification.

### 7. Department Attendance Trend

- Provide daily attendance trends for a department.
- Follow the specified date-range validation and department validation rules.
- Handle missing dates according to the API contract.

### 8. MongoDB and Performance

- Use MongoDB indexes to support uniqueness and frequently used queries.
- Use MongoDB aggregation pipelines for the required analytics.
- Avoid loading entire attendance collections into Python for calculations that should be performed in MongoDB.
- Consider correctness and performance with a dataset much larger than the supplied sample data.

### 9. Documentation

The repository includes documentation for the API contract, data model, code review, and implementation decisions.

- `openapi.yaml`: API endpoints and business rules.
- `DATA_MODEL.md`: MongoDB data model and sample documents.
- `REVIEW.md`: Review of the supplied implementation and identified issues.
- `DECISIONS.md`: Explanation of important technical decisions.

## Prerequisites

- Python 3.11 or newer.
- Git.
- MongoDB 6.0 or newer.
- MongoDB Atlas or a local MongoDB instance.

The assignment grader uses MongoDB 7.0. A MongoDB Atlas free-tier cluster can also be used.

## Local Setup

### 1. Clone the Repository

```bash
git clone https://github.com/pakhisrivastava2122/hrone-employee-attendance-api.git
cd hrone-employee-attendance-api
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root directory and configure:

```env
MONGO_URI=your_mongodb_connection_string
MONGO_DB=attendance_db
```

Replace the placeholder with your own MongoDB connection string.

**Security:** Never commit `.env`, database credentials, or other secrets to GitHub.

### 5. Prepare the Database

Ensure that MongoDB is running and that the connection details are correct.

To load the supplied sample data, run:

```bash
python sample_seed.py
```

The supplied sample dataset contains nine sample documents. The evaluation dataset may be substantially larger and may include edge cases not covered by the samples.

Run the seed script only when appropriate for your database, because it may insert or modify sample records.

### 6. Start the API

```bash
python -m uvicorn app.main:app --reload --port 8000
```

The API should be available at:

- API base URL: `http://127.0.0.1:8000`
- Interactive Swagger documentation: `http://127.0.0.1:8000/docs`

Use Swagger UI to inspect and test the available endpoints.

## Implementation Status and Known Limitations

The implementation should be validated against every applicable requirement in `openapi.yaml`, including R1–R10.

The supplied sample data alone is not sufficient to establish that every edge case or performance requirement is satisfied.

Before submission, verify the following:

- Punch-in and punch-out validation and concurrency behavior.
- Attendance calculations and manual correction rules.
- Audit-trail correctness.
- MongoDB aggregation results for employee and department analytics.
- Leaderboard ranking and tie handling.
- Department trend date handling.
- Missing records, invalid requests, and boundary cases.
- Database indexes and query performance.

**Known limitations or incomplete requirements:**

Add any requirements that remain incomplete or have not been verified here. If all requirements have been tested, replace this note with an accurate statement of the tests performed and their results.

Do not claim that an untested requirement is fully implemented.

## Submission Requirements

The assignment must be submitted through the official submission form provided in the assignment instructions.

The submitted repository must be public and include, at minimum:

- `app/main.py`
- `requirements.txt`
- `REVIEW.md`
- `DECISIONS.md`
- `README.md`

Keep the implementation and documentation consistent with the supplied API contract.

### Submission Checklist

- [ ] The API starts successfully.
- [ ] MongoDB connection settings are configured locally.
- [ ] The required endpoints have been tested.
- [ ] Business rules and edge cases have been reviewed.
- [ ] `REVIEW.md` is completed.
- [ ] `DECISIONS.md` is completed in plain language.
- [ ] Incomplete requirements and known limitations are documented honestly.
- [ ] No `.env` file, credentials, or secrets are committed.
- [ ] No Dockerfile is included.
- [ ] The repository is public and accessible.
- [ ] The repository link is submitted using the official form and the same email address used for the application.



## Repository

GitHub: https://github.com/pakhisrivastava2122/hrone-employee-attendance-api
