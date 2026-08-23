# TestSeries

TestSeries is a web-based application built to make practice-paper preparation easier for CA students.

The application allows ICAI question papers to be uploaded and processed automatically. Extracted questions and suggested answers can then be reviewed, corrected, and organized by subject and chapter. Based on the selected criteria, TestSeries generates a customized question paper along with its corresponding suggested answer sheet.

## Current Version

The current MVP supports the complete workflow from syllabus management to paper generation:

* Subject and chapter management
* ICAI paper upload with metadata and PDF validation
* Automatic question and suggested-answer extraction
* Support for different question formats and MCQs
* Review and correction of extracted questions and answers
* Editable chapter assignment with chapter creation during review
* Persistent storage of corrections
* Chapter-wise question selection and randomized paper generation
* Generated question paper PDF
* Generated suggested answer sheet PDF
* Matching question-to-answer mapping between generated papers
* Complex non-MCQ tables, equations and vector diagrams preserved as visual objects to maintain their original formatting

## Workflow

```text
Manage Subjects & Chapters
          ↓
     Upload Paper
          ↓
   Extract Questions
          ↓
       Review
          ↓
   Correct & Organize
          ↓
    Generate Paper
          ↓
 ┌───────────────────┐
 │ Question Paper    │
 │ Suggested Answers │
 └───────────────────┘
```

## Tech Stack

### Backend

* **Python**
* **Django**
* **Django REST Framework**

### Frontend

* **React**
* **JavaScript**
* **Bootstrap**

### Database

* **PostgreSQL**

### PDF Processing

* **PyMuPDF**
* **pdfplumber**
* **Tesseract OCR**
* **OpenCV**
* **Pillow**

### Document Generation & Processing

* **WeasyPrint**
* **BeautifulSoup**
* **lxml**

### Supporting Technologies

* **Celery**
* **Redis**
* **django-cors-headers**
* **python-dotenv**

## Future Enhancements

The current implementation focuses on the core RTP workflow. Planned extensions include:

* Previous Year Question (PYQ) support
* Mock Test support
* Multi-user authentication
* Cloud deployment

More functionality may be added as the application evolves beyond the current MVP.
