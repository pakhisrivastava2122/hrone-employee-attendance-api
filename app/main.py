
"""
Employee Attendance & Analytics API
Run: uvicorn app.main:app --port 8000
Environment: MONGO_URI, MONGO_DB
"""

import os
import re
import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, OperationFailure
from pymongo.collection import Collection

load_dotenv()

client = MongoClient(
    os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    serverSelectionTimeoutMS=5000,
)
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
PRESENT_STATUSES = {"PRESENT", "WFH", "ON_DUTY"}
ALL_STATUSES = PRESENT_STATUSES | {"ABSENT", "LEAVE"}
MAX_EPOCH_MS = 4102444800000
MIN_EPOCH_MS = 100000000000

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


# ---------------------------------------------------------------------
# Time and serialization helpers
# ---------------------------------------------------------------------

def truncate_seconds(dt: datetime) -> datetime:
    """Normalize a datetime to UTC and discard fractional seconds."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0)


def epoch_ms(dt: Optional[datetime]) -> Optional[int]:
    if dt is None:
        return None
    return int(truncate_seconds(dt).timestamp() * 1000)


def from_epoch_ms(value: Optional[int]) -> Optional[datetime]:
    if value is None:
        return None
    if type(value) is not int or not MIN_EPOCH_MS <= value <= MAX_EPOCH_MS:
        raise ValueError("Timestamp must be a valid epoch-millisecond integer")
    return datetime.fromtimestamp(value / 1000, UTC).replace(microsecond=0)


def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def local_time(dt: datetime) -> datetime:
    return truncate_seconds(dt).astimezone(IST)


def round_half_up(value, places=2):
    quantum = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(422, "Date must be YYYY-MM-DD")
    if parsed.isoformat() != value:
        raise HTTPException(422, "Date must be YYYY-MM-DD")
    return parsed


def parse_month(value: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise HTTPException(422, "Month must be YYYY-MM")
    year, month = map(int, value.split("-"))
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def validate_clock(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"([01]\d|2[0-3]):[0-5]\d", value
    ):
        raise ValueError("Time must use HH:MM (24-hour)")
    return value


def shift_datetime(day: date, clock: str) -> datetime:
    hour, minute = map(int, clock.split(":"))
    return datetime.combine(day, time(hour, minute), IST).astimezone(UTC)


def attendance_date(punch_in: datetime, shift_start: str, shift_end: str) -> str:
    local = local_time(punch_in)
    result = local.date()
    if shift_end <= shift_start and local.strftime("%H:%M") < shift_end:
        result -= timedelta(days=1)
    return result.isoformat()


def compute_late_minutes(punch_in: datetime, shift_start: str) -> int:
    local = local_time(punch_in)
    start = local.replace(
        hour=int(shift_start[:2]),
        minute=int(shift_start[3:]),
        second=0,
        microsecond=0,
    )
    # For an overnight shift, early-morning times belong to yesterday's shift.
    if local < start and local.strftime("%H:%M") < shift_start:
        start -= timedelta(days=1)
    elapsed = int((local - start).total_seconds() // 60)
    return elapsed if (local - start).total_seconds() > 600 else 0


def shift_end_datetime(day: date, shift_start: str, shift_end: str) -> datetime:
    end_day = day + timedelta(days=1) if shift_end <= shift_start else day
    return shift_datetime(end_day, shift_end)


def compute_overtime(punch_out: datetime, shift_end: str, date_str: str,
                     shift_start: str = "09:30") -> int:
    end = shift_end_datetime(parse_date(date_str), shift_start, shift_end)
    minutes = int((truncate_seconds(punch_out) - end).total_seconds() // 60)
    return minutes if minutes >= 30 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    seconds = (truncate_seconds(punch_out) - truncate_seconds(punch_in)).total_seconds()
    return round_half_up(Decimal(str(seconds)) / Decimal(3600), 2)


def public_employee(doc: dict) -> dict:
    return {
        "emp_code": doc["emp_code"],
        "name": doc["name"],
        "email": doc["email"],
        "department": doc["department"],
        "shift_start": doc["shift_start"],
        "shift_end": doc["shift_end"],
        "joined_on": doc["joined_on"],
        "created_at": epoch_ms(doc["created_at"]),
    }


def public_attendance(doc: dict) -> dict:
    def public_history(entry):
        changes = {}
        for field, values in entry.get("changes", {}).items():
            changes[field] = {
                "from": epoch_ms(values["from"])
                if field in ("punch_in", "punch_out") and values.get("from") is not None
                else values.get("from"),
                "to": epoch_ms(values["to"])
                if field in ("punch_in", "punch_out") and values.get("to") is not None
                else values.get("to"),
            }
        return {
            "at": epoch_ms(entry["at"]),
            "by": entry["by"],
            "reason": entry["reason"],
            "changes": changes,
        }

    return {
        "emp_code": doc["emp_code"],
        "date": doc["date"],
        "status": doc["status"],
        "punch_in": epoch_ms(doc.get("punch_in")),
        "punch_out": epoch_ms(doc.get("punch_out")),
        "work_hours": doc.get("work_hours"),
        "late_minutes": doc.get("late_minutes", 0),
        "overtime_minutes": doc.get("overtime_minutes", 0),
        "half_day": doc.get("half_day", False),
        "history": [public_history(e) for e in doc.get("history", [])],
    }


def clean_json(value):
    """Convert BSON values returned by explain into JSON-compatible values."""
    if isinstance(value, datetime):
        return epoch_ms(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    return value


def require_employee(emp_code: str) -> dict:
    employee = db.employees.find_one({"emp_code": emp_code})
    if not employee:
        raise HTTPException(404, "Employee not found")
    return employee


def derived_fields(employee: dict, attendance_day: str,
                   status: str, punch_in: Optional[datetime],
                   punch_out: Optional[datetime]) -> dict:
    if status not in PRESENT_STATUSES:
        return {
            "work_hours": None,
            "late_minutes": 0,
            "overtime_minutes": 0,
            "half_day": False,
        }

    late = compute_late_minutes(punch_in, employee["shift_start"]) if punch_in else 0
    if punch_in is None or punch_out is None:
        return {
            "work_hours": None,
            "late_minutes": late,
            "overtime_minutes": 0,
            "half_day": False,
        }

    hours = compute_work_hours(punch_in, punch_out)
    overtime = compute_overtime(
        punch_out, employee["shift_end"], attendance_day, employee["shift_start"]
    )
    return {
        "work_hours": hours,
        "late_minutes": late,
        "overtime_minutes": overtime,
        "half_day": hours < 4.50,
    }


# ---------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------

class EmployeeIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str

    @field_validator("shift_start", "shift_end")
    @classmethod
    def valid_shift_time(cls, value):
        return validate_clock(value)

    @field_validator("joined_on")
    @classmethod
    def valid_joined_date(cls, value):
        parse_date(value)
        return value

    @field_validator("shift_end")
    @classmethod
    def different_shift_end(cls, value, info):
        start = info.data.get("shift_start")
        if start == value:
            raise ValueError("shift_start and shift_end must differ")
        return value


class PunchInIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    emp_code: str
    punched_at: Optional[int] = None
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"

    @field_validator("punched_at")
    @classmethod
    def valid_timestamp(cls, value):
        if value is not None:
            from_epoch_ms(value)
        return value


class PunchOutIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    emp_code: str
    punched_at: Optional[int] = None

    @field_validator("punched_at")
    @classmethod
    def valid_timestamp(cls, value):
        if value is not None:
            from_epoch_ms(value)
        return value


class RegularizeIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: Optional[Literal["PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE"]] = None
    punch_in: Optional[int] = None
    punch_out: Optional[int] = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)

    @field_validator("punch_in", "punch_out")
    @classmethod
    def valid_timestamp(cls, value):
        if value is not None:
            from_epoch_ms(value)
        return value


# ---------------------------------------------------------------------
# Indexes and health
# ---------------------------------------------------------------------

@app.on_event("startup")
def create_indexes():
    db.employees.create_index([("emp_code", ASCENDING)], unique=True, name="uq_employee_code")
    db.employees.create_index([("department", ASCENDING), ("emp_code", ASCENDING)],
                              name="idx_employee_department_code")
    db.attendance_logs.create_index(
        [("emp_code", ASCENDING), ("date", ASCENDING)],
        unique=True, name="uq_attendance_employee_date"
    )
    db.attendance_logs.create_index(
        [("date", DESCENDING), ("emp_code", ASCENDING)],
        name="idx_attendance_date_employee"
    )
    db.attendance_logs.create_index(
        [("status", ASCENDING), ("date", ASCENDING)],
        name="idx_attendance_status_date"
    )


@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(503, "Database unavailable")


# ---------------------------------------------------------------------
# Employee endpoints
# ---------------------------------------------------------------------

@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    doc = body.model_dump()
    doc["created_at"] = now_utc()
    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")
    return public_employee(doc)


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = {"department": department} if department is not None else {}
    total = db.employees.count_documents(query)
    cursor = (
        db.employees.find(query, {"_id": 0})
        .sort("emp_code", ASCENDING)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [public_employee(d) for d in cursor],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------
# Attendance endpoints
# ---------------------------------------------------------------------

@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    employee = require_employee(body.emp_code)
    ts = from_epoch_ms(body.punched_at) if body.punched_at is not None else now_utc()
    ts = truncate_seconds(ts)
    day = attendance_date(ts, employee["shift_start"], employee["shift_end"])
    doc = {
        "emp_code": body.emp_code,
        "date": day,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, employee["shift_start"]),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Already punched in for this date")
    return public_attendance(doc)


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    employee = require_employee(body.emp_code)
    ts = truncate_seconds(from_epoch_ms(body.punched_at) if body.punched_at is not None else now_utc())

    # Select the most recent open punch at or before this instant.
    record = db.attendance_logs.find_one(
        {
            "emp_code": body.emp_code,
            "punch_in": {"$ne": None, "$lte": ts},
            "punch_out": None,
            "status": {"$in": list(PRESENT_STATUSES)},
        },
        sort=[("punch_in", DESCENDING)],
    )
    if not record:
        # Distinguish a closed record from no open record.
        closed = db.attendance_logs.find_one({
            "emp_code": body.emp_code,
            "punch_in": {"$ne": None, "$lte": ts},
            "punch_out": {"$ne": None},
        }, sort=[("punch_in", DESCENDING)])
        if closed:
            raise HTTPException(409, "Attendance record is already punched out")
        raise HTTPException(404, "No open punch-in found")

    elapsed = (ts - truncate_seconds(record["punch_in"])).total_seconds()
    if elapsed <= 0 or elapsed > 24 * 3600:
        raise HTTPException(422, "Punch-out must be after punch-in and within 24 hours")

    fields = derived_fields(employee, record["date"], record["status"], record["punch_in"], ts)
    updated = db.attendance_logs.find_one_and_update(
        {"emp_code": body.emp_code, "date": record["date"], "punch_out": None},
        {"$set": {"punch_out": ts, **fields}},
        return_document=True,
    )
    if not updated:
        raise HTTPException(409, "Attendance record was already punched out")
    return public_attendance(updated)


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = {}
    if emp_code is not None:
        query["emp_code"] = emp_code
    if status is not None:
        if status not in ALL_STATUSES:
            raise HTTPException(422, "Invalid status")
        query["status"] = status
    if date_from:
        parse_date(date_from)
    if date_to:
        parse_date(date_to)
    if date_from or date_to:
        query["date"] = {}
        if date_from:
            query["date"]["$gte"] = date_from
        if date_to:
            query["date"]["$lte"] = date_to
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must not exceed date_to")

    total = db.attendance_logs.count_documents(query)
    docs = db.attendance_logs.find(query).sort(
        [("date", DESCENDING), ("emp_code", ASCENDING)]
    ).skip((page - 1) * page_size).limit(page_size)
    return {
        "items": [public_attendance(d) for d in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.patch("/attendance/{emp_code}/{date}")
def regularize(emp_code: str, date: str, body: RegularizeIn):
    parse_date(date)
    employee = require_employee(emp_code)
    old = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not old:
        raise HTTPException(404, "Attendance record not found")

    new_status = body.status if body.status is not None else old["status"]
    if new_status in {"ABSENT", "LEAVE"}:
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(422, "ABSENT/LEAVE cannot have punch times")
        new_in = new_out = None
    else:
        new_in = from_epoch_ms(body.punch_in) if body.punch_in is not None else old.get("punch_in")
        new_out = from_epoch_ms(body.punch_out) if body.punch_out is not None else old.get("punch_out")
        if new_in is None:
            raise HTTPException(422, "Presence status requires punch_in")
        if attendance_date(new_in, employee["shift_start"], employee["shift_end"]) != date:
            raise HTTPException(422, "punch_in must belong to the attendance date")
        if new_out is not None:
            seconds = (truncate_seconds(new_out) - truncate_seconds(new_in)).total_seconds()
            if seconds <= 0 or seconds > 24 * 3600:
                raise HTTPException(422, "punch_out must be after punch_in and within 24 hours")

    new_in = truncate_seconds(new_in) if new_in else None
    new_out = truncate_seconds(new_out) if new_out else None
    computed = derived_fields(employee, date, new_status, new_in, new_out)

    old_values = {
        "status": old.get("status"),
        "punch_in": old.get("punch_in"),
        "punch_out": old.get("punch_out"),
        "work_hours": old.get("work_hours"),
        "late_minutes": old.get("late_minutes", 0),
        "overtime_minutes": old.get("overtime_minutes", 0),
        "half_day": old.get("half_day", False),
    }
    new_values = {
        "status": new_status, "punch_in": new_in, "punch_out": new_out, **computed
    }
    changes = {}
    for key, new_value in new_values.items():
        old_value = old_values[key]
        if old_value != new_value:
            changes[key] = {"from": old_value, "to": new_value}
    if not changes:
        raise HTTPException(422, "Request does not change the record")

    history_entry = {
        "at": now_utc(),
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes,
    }
    # Compare-and-set prevents overwriting a concurrent edit and losing history.
    result = db.attendance_logs.update_one(
        {
            "_id": old["_id"],
            "history": old.get("history", []),
            "status": old.get("status"),
            "punch_in": old.get("punch_in"),
            "punch_out": old.get("punch_out"),
        },
        {
            "$set": new_values,
            "$push": {"history": history_entry},
        },
    )
    if result.modified_count != 1:
        raise HTTPException(409, "Record changed concurrently; retry the correction")
    updated = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    return public_attendance(updated)


# ---------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------

def weekdays_between(start: date, end: date) -> int:
    if end < start:
        return 0
    days = (end - start).days + 1
    weeks, rem = divmod(days, 7)
    count = weeks * 5
    for i in range(rem):
        if (start.weekday() + i) % 7 < 5:
            count += 1
    return count


def month_bounds(month: str):
    first, last = parse_month(month)
    return first.isoformat(), (last + timedelta(days=1)).isoformat()


def attendance_month_pipeline(emp_code: str, month: str):
    start, end = month_bounds(month)
    return [
        {"$match": {"emp_code": emp_code, "date": {"$gte": start, "$lt": end}}},
        {"$group": {
            "_id": None,
            "present_days": {"$sum": {"$cond": [
                {"$and": [
                    {"$in": ["$status", list(PRESENT_STATUSES)]},
                    {"$lt": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}}, 7]},
                    {"$gt": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}}, 1]},
                ]},
                {"$cond": [{"$eq": ["$half_day", True]}, 0.5, 1]},
                0,
            ]}},
            "leave_days": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
            "late_count": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}},
            "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
            "total_overtime_minutes": {"$sum": {"$ifNull": ["$overtime_minutes", 0]}},
        }},
    ]


@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")):
    employee = require_employee(emp_code)
    first, last = parse_month(month)
    start_day = max(first, parse_date(employee["joined_on"]))
    working_days = weekdays_between(start_day, last)
    rows = list(db.attendance_logs.aggregate(attendance_month_pipeline(emp_code, month)))
    stats = rows[0] if rows else {}
    present_days = stats.get("present_days", 0)
    pct = round_half_up(present_days / working_days * 100, 4) if working_days else None
    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": stats.get("leave_days", 0),
        "late_count": stats.get("late_count", 0),
        "total_late_minutes": stats.get("total_late_minutes", 0),
        "total_overtime_minutes": stats.get("total_overtime_minutes", 0),
        "attendance_pct": pct,
    }


@app.get("/analytics/departments/summary")
def department_summary(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    department: Optional[str] = None,
):
    start, end = month_bounds(month)
    employee_match = {"joined_on": {"$lt": end}}
    if department is not None:
        employee_match["department"] = department

    pipeline = [
        {"$match": employee_match},
        {"$lookup": {
            "from": "attendance_logs",
            "let": {"code": "$emp_code"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$emp_code", "$$code"]},
                    {"$gte": ["$date", start]},
                    {"$lt": ["$date", end]},
                ]}}},
            ],
            "as": "logs",
        }},
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": "$department",
            "headcount_codes": {"$addToSet": "$emp_code"},
            "present_days": {"$sum": {"$cond": [
                {"$and": [
                    {"$in": ["$logs.status", list(PRESENT_STATUSES)]},
                    {"$ne": ["$logs.date", None]},
                    {"$lt": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$logs.date"}}}, 7]},
                    {"$gt": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$logs.date"}}}, 1]},
                ]},
                {"$cond": [{"$eq": ["$logs.half_day", True]}, 0.5, 1]},
                0,
            ]}},
            "work_hours": {"$avg": {"$cond": [
                {"$ne": ["$logs.work_hours", None]}, "$logs.work_hours", None
            ]}},
            "late_count": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$logs.late_minutes", 0]}, 0]}, 1, 0]}},
            "total_late_minutes": {"$sum": {"$ifNull": ["$logs.late_minutes", 0]}},
            "leave_count": {"$sum": {"$cond": [{"$eq": ["$logs.status", "LEAVE"]}, 1, 0]}},
            "on_duty_count": {"$sum": {"$cond": [{"$eq": ["$logs.status", "ON_DUTY"]}, 1, 0]}},
        }},
        {"$project": {
            "_id": 0, "department": "$_id",
            "headcount": {"$size": "$headcount_codes"},
            "present_days": 1,
            "avg_work_hours": "$work_hours",
            "late_count": 1, "total_late_minutes": 1,
            "leave_count": 1, "on_duty_count": 1,
        }},
        {"$sort": {"department": 1}},
    ]
    items = list(db.employees.aggregate(pipeline))
    for item in items:
        item["present_days"] = round_half_up(item["present_days"], 2)
        if item["avg_work_hours"] is not None:
            item["avg_work_hours"] = round_half_up(item["avg_work_hours"], 2)
    return {"month": month, "items": items}


@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = None,
):
    start, end = month_bounds(month)
    pipeline = [
        {"$match": {"date": {"$gte": start, "$lt": end}}},
        {"$group": {
            "_id": "$emp_code",
            "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
            "late_count": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}},
        }},
        {"$match": {"total_late_minutes": {"$gt": 0}}},
        {"$lookup": {
            "from": "employees", "localField": "_id",
            "foreignField": "emp_code", "as": "employee"
        }},
        {"$unwind": "$employee"},
    ]
    if department is not None:
        pipeline.append({"$match": {"employee.department": department}})
    pipeline += [
        {"$sort": {"total_late_minutes": -1, "_id": 1}},
        {"$setWindowFields": {
            "sortBy": {"total_late_minutes": -1},
            "output": {"rank": {"$rank": {}}},
        }},
        {"$limit": limit},
        {"$project": {
            "_id": 0, "rank": 1, "emp_code": "$_id",
            "name": "$employee.name", "department": "$employee.department",
            "total_late_minutes": 1, "late_count": 1,
        }},
    ]
    return {"month": month, "items": list(db.attendance_logs.aggregate(pipeline))}


@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str,
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
):
    start_day, end_day = parse_date(from_date), parse_date(to_date)
    if start_day > end_day:
        raise HTTPException(422, "'from' must be on or before 'to'")
    if (end_day - start_day).days > 365:
        raise HTTPException(422, "Trend range cannot exceed 366 days")

    # One row per date is generated in MongoDB; dates with no logs are retained.
    pipeline = [
        {"$match": {"department": department, "joined_on": {"$lte": to_date}}},
        {"$lookup": {
            "from": "attendance_logs",
            "let": {"code": "$emp_code"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$emp_code", "$$code"]},
                    {"$gte": ["$date", from_date]},
                    {"$lte": ["$date", to_date]},
                ]}}},
            ],
            "as": "logs",
        }},
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": "$logs.date",
            "present_count": {"$sum": {"$cond": [
                {"$in": ["$logs.status", list(PRESENT_STATUSES)]},
                {"$cond": [{"$eq": ["$logs.half_day", True]}, 0.5, 1]}, 0
            ]}},
            "late_count": {"$sum": {"$cond": [
                {"$gt": [{"$ifNull": ["$logs.late_minutes", 0]}, 0]}, 1, 0
            ]}},
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"_id": 1}},
    ]
    raw = list(db.employees.aggregate(pipeline))
    by_day = {row["_id"]: row for row in raw}

    # Generate the calendar dates and headcount, including dates with no attendance.
    employees = list(db.employees.find({
        "department": department, "joined_on": {"$lte": to_date}
    }, {"_id": 0, "joined_on": 1}))
    items = []
    daily_rates = []
    day = start_day
    while day <= end_day:
        key = day.isoformat()
        headcount = sum(1 for e in employees if e["joined_on"] <= key)
        row = by_day.get(key, {})
        present_count = row.get("present_count", 0)
        working = day.weekday() < 5
        rate = round_half_up(present_count / headcount * 100, 4) if working and headcount else None
        daily_rates.append(rate)
        recent = [v for v in daily_rates[-7:] if v is not None]
        moving = round_half_up(sum(recent) / len(recent), 4) if recent else None
        items.append({
            "date": key,
            "is_working_day": working,
            "headcount": headcount,
            "present_count": round_half_up(present_count, 2),
            "late_count": row.get("late_count", 0),
            "attendance_rate": rate,
            "moving_avg_7d": moving,
        })
        day += timedelta(days=1)
    return {"department": department, "items": items}


# ---------------------------------------------------------------------
# MongoDB explain endpoint
# ---------------------------------------------------------------------

@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: Literal[
        "attendance_list", "employee_monthly", "department_summary",
        "late_leaderboard", "department_trend"
    ],
    emp_code: Optional[str] = None,
    month: Optional[str] = None,
    department: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    status: Optional[str] = None,
):
    if endpoint == "attendance_list":
        query = {}
        if emp_code:
            query["emp_code"] = emp_code
        if status:
            if status not in ALL_STATUSES:
                raise HTTPException(422, "Invalid status")
            query["status"] = status
        if date_from or date_to:
            query["date"] = {}
            if date_from:
                parse_date(date_from)
                query["date"]["$gte"] = date_from
            if date_to:
                parse_date(date_to)
                query["date"]["$lte"] = date_to
        collection = db.attendance_logs
        command = {
            "find": collection.name,
            "filter": query,
            "sort": {"date": -1, "emp_code": 1},
            "limit": 20,
        }
    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(422, "emp_code and month are required")
        require_employee(emp_code)
        start, end = month_bounds(month)
        collection = db.attendance_logs
        command = {
            "aggregate": collection.name,
            "pipeline": attendance_month_pipeline(emp_code, month),
            "cursor": {},
        }
    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(422, "month is required")
        start, end = month_bounds(month)
        match = {"joined_on": {"$lt": end}}
        if department:
            match["department"] = department
        collection = db.employees
        command = {"aggregate": collection.name, "pipeline": [
            {"$match": match},
            {"$sort": {"department": 1}},
        ], "cursor": {}}
    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(422, "month is required")
        start, end = month_bounds(month)
        collection = db.attendance_logs
        command = {"aggregate": collection.name, "pipeline": [
            {"$match": {"date": {"$gte": start, "$lt": end}}},
            {"$sort": {"late_minutes": -1}},
            {"$limit": limit},
        ], "cursor": {}}
    else:
        if not department or not from_date or not to_date:
            raise HTTPException(422, "department, from and to are required")
        parse_date(from_date)
        parse_date(to_date)
        collection = db.employees
        command = {"aggregate": collection.name, "pipeline": [
            {"$match": {"department": department, "joined_on": {"$lte": to_date}}},
            {"$sort": {"joined_on": 1}},
        ], "cursor": {}}

    try:
        result = db.command({"explain": command, "verbosity": "executionStats"})
    except OperationFailure as exc:
        raise HTTPException(400, f"Explain failed: {exc.details.get('errmsg', str(exc))}")
    return {
        "endpoint": endpoint,
        "collection": collection.name,
        "explain": clean_json(result),
    }
