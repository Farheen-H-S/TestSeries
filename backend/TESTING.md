## Syllabus app
- Migrations successful
- Admin working - correct
- Subject creation - correct
- Chapter creation - correct
- UNIQUE constraint - correct
- PROTECT behavior - correct
- http://localhost:8000/api/v1/subjects/ - correct
- http://localhost:8000/api/v1/subjects/1/chapters/ - correct (404 if subject is inactive)

## Documents app

Status: Partially Verified

Tests Performed:
- Endpoint reachable.
- Serializer validation executed.
- Metadata fields accepted.
- Request reached the upload view.

Issue Encountered:
- Thunder Client returned:
  "file": ["No file was submitted."]
- The backend did not receive the uploaded PDF in request.FILES.
- This appears to be a client-side multipart/form-data issue rather than a backend routing or serializer issue.

Verification Pending:
- Successful multipart upload using a different API client (Postman/cURL/Insomnia) or frontend integration.