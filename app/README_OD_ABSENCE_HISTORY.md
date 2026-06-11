OD/Absence history endpoints missing

Frontend expects:
- GET /students/od/history
- GET /students/absent/history

Currently not present in presence-backend/app/routes_students.py.

Implement these endpoints using ODRequest and AbsenceRequest filtered by student_id from JWT (student_required).
Return JSON payload:
{
  "requests": [
    {
      "id": ...,
      "date" or "request_date": "YYYY-MM-DD",
      "category": "FULL_DAY" | "SLOT",
      "slots": "comma-separated slot names" (or null),
      "reason": ...,
      "status": "PENDING" | "APPROVED" | "REJECTED",
      "proof_url": ...,
      "cr_remarks": ...
    }
  ]
}

