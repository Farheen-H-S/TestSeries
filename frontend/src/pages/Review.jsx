import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import documentService from '../services/documentService';
import questionService from '../services/questionService';
import Button from '../components/common/Button';
import EmptyState from '../components/common/EmptyState';
import './Review.css';

// Helper to strip HTML tags safely for text preview
const stripHtml = (htmlString) => {
  if (!htmlString) return '';
  try {
    const doc = new DOMParser().parseFromString(htmlString, 'text/html');
    return doc.body.textContent || '';
  } catch (e) {
    // Fallback if DOMParser fails or is unavailable
    return htmlString.replace(/<\/?[^>]+(>|$)/g, "");
  }
};

const Review = () => {
  const { documentId } = useParams();
  const navigate = useNavigate();
  
  // State variables
  const [document, setDocument] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Filtering and Sorting state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL'); // 'ALL', 'ANSWERED', 'MISSING'
  const [marksFilter, setMarksFilter] = useState('ALL'); // 'ALL' or a specific numeric string
  const [sortBy, setSortBy] = useState('Q_NUM_ASC'); // 'Q_NUM_ASC', 'Q_NUM_DESC', 'MARKS_ASC', 'MARKS_DESC'
  
  // Expanded states for cards (keyed by question_id)
  const [expandedCards, setExpandedCards] = useState({});

  // Fetch both document details and questions concurrently (wrapped in useCallback to prevent recreate triggers)
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [docData, questionsData] = await Promise.all([
        documentService.getDocument(documentId),
        questionService.getQuestions(documentId)
      ]);
      
      setDocument(docData);
      setQuestions(questionsData);
    } catch (err) {
      console.error('Error fetching review data:', err);
      setError('Unable to load this document.');
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Toggle expanded state for a single question card
  const toggleCard = (qId) => {
    setExpandedCards(prev => ({
      ...prev,
      [qId]: !prev[qId]
    }));
  };

  // Helper to check if an answer is missing/empty
  const isAnswerMissing = (answerText) => {
    return answerText === null || answerText === undefined || answerText.trim() === '';
  };

  // 1. Statistics Calculations (based on all fetched questions)
  const stats = useMemo(() => {
    const total = questions.length;
    const withAnswers = questions.filter(q => !isAnswerMissing(q.answer_text)).length;
    const withoutAnswers = total - withAnswers;
    return { total, withAnswers, withoutAnswers };
  }, [questions]);

  // 2. Extract dynamic marks options from current questions
  const marksOptions = useMemo(() => {
    const marksSet = new Set();
    questions.forEach(q => {
      if (q.marks !== null && q.marks !== undefined) {
        marksSet.add(q.marks);
      }
    });
    return Array.from(marksSet).sort((a, b) => a - b);
  }, [questions]);

  // 3. Filtering and Sorting logic (client-side only for speed)
  const processedQuestions = useMemo(() => {
    let result = [...questions];

    // Filter by search query (case-insensitive search on question_text only)
    if (searchQuery.trim() !== '') {
      const query = searchQuery.toLowerCase();
      result = result.filter(q => 
        q.question_text && q.question_text.toLowerCase().includes(query)
      );
    }

    // Filter by answer status
    if (statusFilter === 'ANSWERED') {
      result = result.filter(q => !isAnswerMissing(q.answer_text));
    } else if (statusFilter === 'MISSING') {
      result = result.filter(q => isAnswerMissing(q.answer_text));
    }

    // Filter by marks
    if (marksFilter !== 'ALL') {
      const targetMarks = parseInt(marksFilter, 10);
      result = result.filter(q => q.marks === targetMarks);
    }

    // Sorting logic
    result.sort((a, b) => {
      if (sortBy === 'Q_NUM_ASC' || sortBy === 'Q_NUM_DESC') {
        const numA = a.question_number || '';
        const numB = b.question_number || '';
        const comparison = numA.localeCompare(numB, undefined, { numeric: true, sensitivity: 'base' });
        return sortBy === 'Q_NUM_ASC' ? comparison : -comparison;
      }
      
      if (sortBy === 'MARKS_ASC' || sortBy === 'MARKS_DESC') {
        const marksA = a.marks ?? Number.POSITIVE_INFINITY;
        const marksB = b.marks ?? Number.POSITIVE_INFINITY;
        if (marksA === marksB) {
          // Secondary sort by question number if marks are equal
          return (a.question_number || '').localeCompare(b.question_number || '', undefined, { numeric: true });
        }
        if (sortBy === 'MARKS_ASC') {
          return marksA < marksB ? -1 : 1;
        } else {
          return marksA > marksB ? -1 : 1;
        }
      }

      return 0;
    });

    return result;
  }, [questions, searchQuery, statusFilter, marksFilter, sortBy]);

  // Navigate back to documents list
  const handleBackToDocuments = () => {
    navigate('/');
  };

  // Helper class resolver for extraction status
  const getStatusColorClass = (status) => {
    switch (status) {
      case 'COMPLETED': return 'status-completed-text';
      case 'FAILED': return 'status-failed-text';
      default: return 'status-processing-text';
    }
  };

  // Generate the collapsed preview safely from question_content or question_text
  const getQuestionPreview = (q) => {
    if (q.question_content && q.question_content.trim() !== '') {
      return stripHtml(q.question_content);
    }
    return q.question_text || '';
  };

  // Reset all filters in client-side search toolbar
  const handleClearFilters = () => {
    setSearchQuery('');
    setStatusFilter('ALL');
    setMarksFilter('ALL');
  };

  // Loading skeleton placeholder render helper
  if (loading) {
    return (
      <div className="review-container">
        <div className="review-header">
          <div className="skeleton-block skeleton-text skeleton-header-title"></div>
          <div className="skeleton-block skeleton-text skeleton-back-btn"></div>
        </div>

        <div className="overview-section">
          <div className="skeleton-card skeleton-block"></div>
          <div className="skeleton-card skeleton-block"></div>
        </div>

        <div className="skeleton-card skeleton-block skeleton-toolbar"></div>

        <div className="skeleton-container">
          <div className="skeleton-list-item skeleton-block"></div>
          <div className="skeleton-list-item skeleton-block"></div>
          <div className="skeleton-list-item skeleton-block"></div>
        </div>
      </div>
    );
  }

  // Error State Render
  if (error) {
    return (
      <div className="error-state-card">
        <h2 className="error-state-title">Unable to load this document.</h2>
        <p className="error-state-desc">The request failed. Please check your connection or retry loading the document detail.</p>
        <div className="error-actions">
          <Button variant="outline" onClick={handleBackToDocuments}>
            Back to Documents
          </Button>
          <Button variant="primary" onClick={fetchData}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // Empty State Render (No document metadata found or document doesn't exist)
  if (!document) {
    return (
      <div className="error-state-card">
        <h2 className="error-state-title">Unable to locate document metadata.</h2>
        <p className="error-state-desc">The requested document might have been removed or does not exist.</p>
        <Button variant="primary" onClick={handleBackToDocuments}>
          Back to Documents
        </Button>
      </div>
    );
  }

  // Date formatter helper
  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const options = { year: 'numeric', month: 'short', day: 'numeric' };
      return new Date(dateStr).toLocaleDateString(undefined, options);
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="review-container">
      {/* Top Header */}
      <div className="review-header">
        <h1 className="review-header-title">Review Paper</h1>
        <Button variant="outline" onClick={handleBackToDocuments}>
          Back to Documents
        </Button>
      </div>

      {/* Document Overview Layout */}
      <section className="overview-section">
        {/* Metadata Details Card */}
        <div className="overview-card">
          <h3 className="overview-card-title">Document Overview</h3>
          <div className="metadata-grid">
            <div className="metadata-item">
              <span className="metadata-label">Title</span>
              <span className="metadata-value highlight">{document.title || '—'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Subject</span>
              <span className="metadata-value">{document.subject?.name || '—'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Exam Level</span>
              <span className="metadata-value">{document.subject?.exam_level || '—'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Document Type</span>
              <span className="metadata-value">{document.document_type || '—'}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Paper Year / Session</span>
              <span className="metadata-value">
                {document.paper_year || '—'} {document.paper_session ? `/ ${document.paper_session}` : ''}
              </span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Uploaded Date</span>
              <span className="metadata-value">{formatDate(document.uploaded_at)}</span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Extraction Status</span>
              <span className={`metadata-value highlight ${getStatusColorClass(document.extraction_status)}`}>
                {document.extraction_status || '—'}
              </span>
            </div>
            <div className="metadata-item">
              <span className="metadata-label">Total Pages</span>
              <span className="metadata-value highlight">{document.total_pages ?? '—'}</span>
            </div>
          </div>
        </div>

        {/* Statistics Overview Card */}
        <div className="overview-card">
          <h3 className="overview-card-title">Extraction Results</h3>
          <div className="stats-grid">
            <div className="stat-item">
              <span className="stat-number">{stats.total}</span>
              <span className="stat-label">Questions Extracted</span>
            </div>
            <div className="stat-item">
              <span className="stat-number">{stats.withAnswers}</span>
              <span className="stat-label">Questions with Answers</span>
            </div>
            <div className="stat-item">
              <span className="stat-number">{stats.withoutAnswers}</span>
              <span className="stat-label">Questions without Answers</span>
            </div>
          </div>
        </div>
      </section>

      {/* Filters & Sorting Toolbar */}
      <section className="toolbar-card">
        <div className="toolbar-grid">
          {/* Search Box */}
          <div className="toolbar-field-group">
            <label htmlFor="search" className="toolbar-field-label">Search</label>
            <input
              id="search"
              type="text"
              className="input-field"
              placeholder="Search question text..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Status Tab Group */}
          <div className="toolbar-field-group">
            <label className="toolbar-field-label">Answer Status</label>
            <div className="status-filter-group">
              <button 
                className={`status-tab-btn ${statusFilter === 'ALL' ? 'active' : ''}`}
                onClick={() => setStatusFilter('ALL')}
              >
                All
              </button>
              <button 
                className={`status-tab-btn ${statusFilter === 'ANSWERED' ? 'active' : ''}`}
                onClick={() => setStatusFilter('ANSWERED')}
              >
                Answered
              </button>
              <button 
                className={`status-tab-btn ${statusFilter === 'MISSING' ? 'active' : ''}`}
                onClick={() => setStatusFilter('MISSING')}
              >
                Missing
              </button>
            </div>
          </div>

          {/* Dynamic Marks Filter */}
          <div className="toolbar-field-group">
            <label htmlFor="marks-filter" className="toolbar-field-label">Marks</label>
            <div className="select-wrapper">
              <select
                id="marks-filter"
                className="select-field"
                value={marksFilter}
                onChange={(e) => setMarksFilter(e.target.value)}
              >
                <option value="ALL">All Marks</option>
                {marksOptions.map(marks => (
                  <option key={marks} value={marks.toString()}>
                    {marks} Marks
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Sorting Dropdown */}
          <div className="toolbar-field-group">
            <label htmlFor="sort-by" className="toolbar-field-label">Sort By</label>
            <div className="select-wrapper">
              <select
                id="sort-by"
                className="select-field"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
              >
                <option value="Q_NUM_ASC">Question Number (Asc)</option>
                <option value="Q_NUM_DESC">Question Number (Desc)</option>
                <option value="MARKS_ASC">Marks (Asc)</option>
                <option value="MARKS_DESC">Marks (Desc)</option>
              </select>
            </div>
          </div>
        </div>
      </section>

      {/* Extracted Questions list */}
      <section className="questions-section">
        <div className="questions-count-label">
          <span>Questions list</span>
          <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
            Showing {processedQuestions.length} of {stats.total}
          </span>
        </div>

        {questions.length === 0 ? (
          <EmptyState
            title="No questions extracted"
            message="No questions were extracted from this document. The extraction may have failed or produced no usable content."
            actionText="Back to Documents"
            onAction={handleBackToDocuments}
          />
        ) : processedQuestions.length === 0 ? (
          <EmptyState
            title="No questions match filters"
            message="No questions were extracted from this document that match your current search, answer status, or marks filter settings."
            actionText="Clear Filters"
            onAction={handleClearFilters}
          />
        ) : (
          processedQuestions.map((q) => {
            const isExpanded = !!expandedCards[q.question_id];
            const answerMissing = isAnswerMissing(q.answer_text);
            const questionPreview = getQuestionPreview(q);
            
            return (
              <div 
                key={q.question_id} 
                className={`question-review-card ${isExpanded ? 'expanded' : ''}`}
              >
                {/* Header: Clickable triggers expansion */}
                <div 
                  className="question-card-header"
                  onClick={() => toggleCard(q.question_id)}
                >
                  <div className="question-header-left">
                    <span className="question-number-title">
                      Question {q.question_number ?? '—'}
                    </span>
                    {q.marks !== null && q.marks !== undefined && (
                      <span className="doc-type-badge" style={{ textTransform: 'lowercase' }}>
                        {q.marks} marks
                      </span>
                    )}
                  </div>
                  <div className="question-header-right">
                    <span className={`question-badge ${answerMissing ? 'badge-missing' : 'badge-available'}`}>
                      {answerMissing ? 'Answer missing' : 'Answer available'}
                    </span>
                    {/* Chevron arrow icon */}
                    <svg viewBox="0 0 24 24" className="chevron-icon" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                  </div>
                </div>

                {/* Collapsed Snippet Preview */}
                {!isExpanded && questionPreview && (
                  <div className="question-preview-content">
                    {questionPreview}
                  </div>
                )}

                {/* Expanded content */}
                {isExpanded && (
                  <div className="question-card-body">
                    {/* Chapter Detail */}
                    <div className="question-field-group">
                      <span className="question-field-label">Chapter</span>
                      <span className="metadata-value" style={{ fontWeight: 600 }}>
                        {q.chapter_name || 'Not Assigned'}
                      </span>
                    </div>

                    {/* Question text box */}
                    <div className="question-field-group">
                      <span className="question-field-label">Question</span>
                      {q.question_content ? (
                        <div 
                          className="question-text-box"
                          dangerouslySetInnerHTML={{ __html: q.question_content }}
                        />
                      ) : (
                        <div className="question-text-box">
                          {q.question_text || '—'}
                        </div>
                      )}
                    </div>

                    {/* Answer text box */}
                    <div className="question-field-group">
                      <span className="question-field-label">Answer</span>
                      {answerMissing ? (
                        <div className="question-text-box warning-box">
                          Answer not available
                        </div>
                      ) : q.answer_content ? (
                        <div 
                          className="question-text-box"
                          dangerouslySetInnerHTML={{ __html: q.answer_content }}
                        />
                      ) : (
                        <div className="question-text-box">
                          {q.answer_text}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </section>
    </div>
  );
};

export default Review;
