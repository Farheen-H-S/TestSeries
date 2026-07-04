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

## Extraction app (phase 1 - infra)
- Migrations successful
- Admin working - correct
- Log creation - correct
- GET http://127.0.0.1:8000/api/v1/extraction-logs/ - correct

Test: Foreign key cascade delete

Steps:
1. Created a Document.
2. Created one or more ExtractionLog records linked to that document.
3. Deleted the Document from Django Admin.

Expected Result:
All linked ExtractionLog records should also be deleted.

Actual Result:
Document and all associated ExtractionLog records were deleted successfully.

Status:
PASS

## Papers app
- migrations successfull
- admin working - correct
- GET http://127.0.0.1:8000/api/v1/questions/ - correct
- GET http://127.0.0.1:8000/api/v1/generated-papers/ - correct
- GET http://127.0.0.1:8000/api/v1/generated-paper-questions/