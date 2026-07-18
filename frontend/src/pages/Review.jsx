import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate, useBlocker, useBeforeUnload } from 'react-router-dom';
import documentService from '../services/documentService';
import questionService from '../services/questionService';
import subjectService from '../services/subjectService';
import Button from '../components/common/Button';
import EmptyState from '../components/common/EmptyState';
import SearchableSelect from '../components/common/SearchableSelect';
import './Review.css';

// Helper to strip HTML tags safely for text preview
const stripHtml = (htmlString) => {
  if (!htmlString) return '';
  try {
    const doc = new DOMParser().parseFromString(htmlString, 'text/html');
    return doc.body.textContent || '';
  } catch (e) {
    return htmlString.replace(/<\/?[^>]+(>|$)/g, "");
  }
};

const Review = () => {
  const { documentId } = useParams();
  const navigate = useNavigate();
  
  // State variables
  const [document, setDocument] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [logs, setLogs] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Filtering and Sorting state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL'); // 'ALL', 'ANSWERED', 'MISSING'
  const [marksFilter, setMarksFilter] = useState('ALL'); // 'ALL' or a specific numeric string
  const [sortBy, setSortBy] = useState('Q_NUM_ASC'); // 'Q_NUM_ASC', 'Q_NUM_DESC', 'MARKS_ASC', 'MARKS_DESC'
  
  // Expanded states for cards (keyed by question_id)
  const [expandedCards, setExpandedCards] = useState({});

  // Inline Question Edit States
  const [editingQuestionId, setEditingQuestionId] = useState(null);
  const [editForm, setEditForm] = useState({
    question_number: '',
    question_text: '',
    answer_text: '',
    chapter: ''
  });
  const [editErrors, setEditErrors] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  const [editGeneralError, setEditGeneralError] = useState(null);

  // Inline Chapter Creation States
  const [pendingChapterName, setPendingChapterName] = useState('');
  const [isCreatingChapter, setIsCreatingChapter] = useState(false);
  const [chapterCreationError, setChapterCreationError] = useState(null);

  // Fetch document, questions, logs, and subject chapters
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [docData, questionsData, logsData] = await Promise.all([
        documentService.getDocument(documentId),
        questionService.getQuestions(documentId),
        documentService.getExtractionLogs(documentId)
      ]);
      
      setDocument(docData);
      setQuestions(questionsData);
      setLogs(logsData);

      if (docData?.subject?.subject_id) {
        const chaptersData = await subjectService.getSubjectChapters(docData.subject.subject_id);
        setChapters(chaptersData);
      }
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

  // Check if the current edit form is actually dirty compared to the original values
  const isFormDirty = useMemo(() => {
    if (editingQuestionId === null) return false;
    const originalQ = questions.find(q => q.question_id === editingQuestionId);
    if (!originalQ) return false;
    
    return (
      String(editForm.question_number ?? '') !== String(originalQ.question_number ?? '') ||
      String(editForm.question_text ?? '') !== String(originalQ.question_text ?? '') ||
      String(editForm.answer_text ?? '') !== String(originalQ.answer_text ?? '') ||
      String(editForm.chapter ?? '') !== String(originalQ.chapter ?? '')
    );
  }, [editingQuestionId, editForm, questions]);

  // React Router v7 SPA Navigation Blocker
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isFormDirty && currentLocation.pathname !== nextLocation.pathname
  );

  useEffect(() => {
    if (blocker.state === 'blocked') {
      const confirmLeave = window.confirm(
        'You have unsaved changes. Are you sure you want to leave?'
      );
      if (confirmLeave) {
        blocker.proceed();
      } else {
        blocker.reset();
      }
    }
  }, [blocker, isFormDirty]);

  // Browser reload / tab close warning
  useBeforeUnload(
    useCallback(
      (e) => {
        if (isFormDirty) {
          e.preventDefault();
        }
      },
      [isFormDirty]
    )
  );

  // Toggle expanded state for a single question card
  const toggleCard = (qId) => {
    if (isFormDirty && editingQuestionId !== qId) {
      const confirmDiscard = window.confirm('You have unsaved edits on another question. Discard changes?');
      if (!confirmDiscard) return;
      setEditingQuestionId(null);
    } else if (editingQuestionId !== null && editingQuestionId !== qId) {
      setEditingQuestionId(null);
    }
    setExpandedCards(prev => ({
      ...prev,
      [qId]: !prev[qId]
    }));
  };

  // Helper to check if an answer is missing/empty
  const isAnswerMissing = (answerText) => {
    return answerText === null || answerText === undefined || answerText.trim() === '';
  };

  // Statistics Calculations
  // Statistics Calculations
  const stats = useMemo(() => {
    const reviewableQuestions = questions.filter(q => {
      const hasContent = (q.question_text && q.question_text.trim() !== '') || (q.question_content && q.question_content.trim() !== '');
      const isContainer = questions.some(child => child.parent_question === q.question_id);
      return hasContent || !isContainer;
    });
    const total = questions.length;
    const reviewable = reviewableQuestions.length;
    const withAnswers = reviewableQuestions.filter(q => !isAnswerMissing(q.answer_text)).length;
    const withoutAnswers = reviewable - withAnswers;
    return { total, reviewable, withAnswers, withoutAnswers };
  }, [questions]);

  // Diagnostics Calculations
  const diagnostics = useMemo(() => {
    if (!logs || logs.length === 0) return null;
    const completedLog = logs.find(l => l.status === 'COMPLETED');
    if (!completedLog || !completedLog.message) return null;
    
    const message = completedLog.message;
    const durationMatch = message.match(/in ([\d.]+)s/);
    const duration = durationMatch ? `${durationMatch[1]}s` : '—';
    
    const matchesMatch = message.match(/Matches: (\d+)/);
    const matches = matchesMatch ? matchesMatch[1] : '—';
    
    const rejectionsMatch = message.match(/Rejections: (.*)$/);
    const rejections = [];
    if (rejectionsMatch && rejectionsMatch[1]) {
      const parts = rejectionsMatch[1].split(', ');
      parts.forEach(part => {
        const m = part.match(/(.+) \((\d+)\)/);
        if (m) {
          rejections.push({
            reason: m[1],
            count: parseInt(m[2], 10)
          });
        }
      });
    }
    
    return { duration, matches, rejections, raw: message };
  }, [logs]);

  // Extract dynamic marks options
  const marksOptions = useMemo(() => {
    const marksSet = new Set();
    questions.forEach(q => {
      if (q.marks !== null && q.marks !== undefined) {
        marksSet.add(q.marks);
      }
    });
    return Array.from(marksSet).sort((a, b) => a - b);
  }, [questions]);

  // Filtering and Sorting logic
  const processedQuestions = useMemo(() => {
    // Hide parent container questions only if they have no text/content of their own
    let result = questions.filter(q => {
      const hasContent = (q.question_text && q.question_text.trim() !== '') || (q.question_content && q.question_content.trim() !== '');
      const isContainer = questions.some(child => child.parent_question === q.question_id);
      return hasContent || !isContainer;
    });

    if (searchQuery.trim() !== '') {
      const query = searchQuery.toLowerCase();
      result = result.filter(q => 
        (q.question_text && q.question_text.toLowerCase().includes(query)) ||
        (q.question_number && q.question_number.toLowerCase().includes(query)) ||
        (q.answer_text && q.answer_text.toLowerCase().includes(query)) ||
        (q.chapter_name && q.chapter_name.toLowerCase().includes(query))
      );
    }

    if (statusFilter === 'ANSWERED') {
      result = result.filter(q => !isAnswerMissing(q.answer_text));
    } else if (statusFilter === 'MISSING') {
      result = result.filter(q => isAnswerMissing(q.answer_text));
    }

    if (marksFilter !== 'ALL') {
      const targetMarks = parseInt(marksFilter, 10);
      result = result.filter(q => q.marks === targetMarks);
    }

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

  // Navigation handlers
  const handleBackToDocuments = () => {
    if (isFormDirty) {
      if (window.confirm("You have unsaved changes. Are you sure you want to leave?")) {
        setEditingQuestionId(null);
        navigate('/');
      }
    } else {
      setEditingQuestionId(null);
      navigate('/');
    }
  };

  const handleClearFilters = () => {
    setSearchQuery('');
    setStatusFilter('ALL');
    setMarksFilter('ALL');
  };

  // Card-Level Edit Handlers
  const startEditQuestion = (q, e) => {
    e.stopPropagation(); // Avoid collapsing the card
    setEditErrors({});
    setEditGeneralError(null);
    setEditingQuestionId(q.question_id);
    setEditForm({
      question_number: q.question_number || '',
      question_text: q.question_text || '',
      answer_text: q.answer_text || '',
      chapter: q.chapter || ''
    });
  };

  const cancelEditQuestion = (e) => {
    if (e) e.stopPropagation();
    setEditingQuestionId(null);
    setEditErrors({});
    setEditGeneralError(null);
  };

  const handleFormChange = (e) => {
    const { name, value } = e.target;
    setEditForm(prev => ({ ...prev, [name]: value }));
    if (editErrors[name]) {
      setEditErrors(prev => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  };

  const handleChapterDropdownChange = (e) => {
    const val = e.target.value;
    setEditForm(prev => ({ ...prev, chapter: val }));
    if (editErrors.chapter) {
      setEditErrors(prev => {
        const next = { ...prev };
        delete next.chapter;
        return next;
      });
    }
  };

  const validateEditForm = () => {
    const errors = {};
    if (!editForm.question_number.trim()) {
      errors.question_number = 'Question number is required.';
    }
    if (!editForm.question_text.trim()) {
      errors.question_text = 'Question content is required.';
    }
    if (!editForm.answer_text.trim()) {
      errors.answer_text = 'Answer content is required.';
    }
    if (!editForm.chapter) {
      errors.chapter = 'Chapter mapping is required.';
    }
    return errors;
  };

  const saveEditQuestion = async (qId, e) => {
    if (e) e.stopPropagation();
    const errors = validateEditForm();
    if (Object.keys(errors).length > 0) {
      setEditErrors(errors);
      return;
    }

    setIsSaving(true);
    setEditGeneralError(null);

    try {
      const updatedQ = await questionService.updateQuestion(qId, {
        question_number: editForm.question_number.trim(),
        question_text: editForm.question_text,
        answer_text: editForm.answer_text,
        chapter: Number(editForm.chapter)
      });

      // Update question locally inside state (no reload)
      setQuestions(prev => prev.map(q => q.question_id === qId ? updatedQ : q));
      setEditingQuestionId(null);
    } catch (err) {
      console.error('Error saving question edits:', err);
      if (err.response && err.response.status === 400) {
        const fieldErrors = err.response.data;
        const mappedErrors = {};
        Object.keys(fieldErrors).forEach(key => {
          if (key === 'non_field_errors') {
            setEditGeneralError(Array.isArray(fieldErrors[key]) ? fieldErrors[key][0] : fieldErrors[key]);
          } else {
            mappedErrors[key] = Array.isArray(fieldErrors[key]) ? fieldErrors[key][0] : fieldErrors[key];
          }
        });
        setEditErrors(mappedErrors);
      } else {
        setEditGeneralError(err.response?.data?.detail || 'An unexpected error occurred while saving.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  // Inline Chapter Creation logic
  const handleCreateChapterPrompt = (chapterName) => {
    setPendingChapterName(chapterName);
    setChapterCreationError(null);
  };

  const confirmCreateChapter = async () => {
    if (!pendingChapterName.trim() || !document?.subject?.subject_id) return;
    setIsCreatingChapter(true);
    setChapterCreationError(null);

    try {
      const newChapter = await subjectService.createChapter(document.subject.subject_id, {
        chapter_name: pendingChapterName.trim()
      });

      // Update local chapters list (sorted) and select it in the form
      setChapters(prev => 
        [...prev, newChapter].sort((a, b) => 
          a.chapter_name.localeCompare(b.chapter_name, undefined, { numeric: true, sensitivity: 'base' })
        )
      );
      setEditForm(prev => ({ ...prev, chapter: newChapter.chapter_id }));
      setPendingChapterName('');
    } catch (err) {
      console.error('Error creating chapter inline:', err);
      setChapterCreationError(err.response?.data?.chapter_name || err.response?.data?.detail || 'Duplicate or invalid chapter name.');
    } finally {
      setIsCreatingChapter(false);
    }
  };

  const getStatusColorClass = (status) => {
    switch (status) {
      case 'COMPLETED': return 'status-completed-text';
      case 'FAILED': return 'status-failed-text';
      default: return 'status-processing-text';
    }
  };

  const getQuestionPreview = (q) => {
    if (q.question_content && q.question_content.trim() !== '') {
      return stripHtml(q.question_content);
    }
    return q.question_text || '';
  };

  const formatCardDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const options = { year: 'numeric', month: 'short', day: 'numeric' };
      return new Date(dateStr).toLocaleDateString(undefined, options);
    } catch {
      return dateStr;
    }
  };

  const chapterOptions = chapters.map(ch => ({
    value: ch.chapter_id,
    label: ch.chapter_name
  }));

  // Loading skeleton
  if (loading) {
    return (
      <div className="review-split-layout">
        <div className="pdf-panel-loading skeleton-block"></div>
        <div className="review-panel review-container">
          <div className="review-header">
            <div className="skeleton-block skeleton-text skeleton-header-title"></div>
          </div>
          <div className="skeleton-card skeleton-block"></div>
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
        <p className="error-state-desc">The request failed. Please check your connection or retry loading.</p>
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

  // Empty State
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

  return (
    <div className="review-split-layout">
      {/* LEFT COLUMN: PDF VIEWER PANEL */}
      <section className="pdf-viewer-panel">
        {document.file_url ? (
          <iframe
            src={`${document.file_url}#toolbar=0`}
            title={document.title}
            className="pdf-iframe-frame"
          />
        ) : (
          <div className="pdf-no-file-msg">PDF file is not available.</div>
        )}
      </section>

      {/* RIGHT COLUMN: REVIEW LIST PANEL */}
      <section className="review-panel-scrollable">
        <div className="review-container">
          {/* Top Informational Banner */}
          <div className="review-info-banner">
            <svg className="info-banner-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            <p className="info-banner-text">
              Review extracted content before using it. Correcting OCR errors and assigning the correct chapters improves the accuracy of generated question papers and future extraction quality.
            </p>
          </div>

          {/* Top Header */}
          <div className="review-header">
            <h2 className="review-header-title">Review Extracted Paper</h2>
            <Button variant="outline" onClick={handleBackToDocuments}>
              Back to Documents
            </Button>
          </div>

          {/* Document Overview Layout */}
          <section className="overview-section">
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
                  <span className="metadata-label">Paper Year / Month</span>
                  <span className="metadata-value">
                    {document.paper_year || '—'} {document.exam_month ? `/ ${document.exam_month}` : ''}
                  </span>
                </div>
                <div className="metadata-item">
                  <span className="metadata-label">Extraction Status</span>
                  <span className={`metadata-value highlight ${getStatusColorClass(document.extraction_status)}`}>
                    {document.extraction_status || '—'}
                  </span>
                </div>
              </div>
            </div>

            {/* Statistics Card */}
            <div className="overview-card">
              <h3 className="overview-card-title">Extraction Results</h3>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-number">{stats.total}</span>
                  <span className="stat-label">Total Extracted</span>
                </div>
                <div className="stat-item">
                  <span className="stat-number">{stats.reviewable}</span>
                  <span className="stat-label">Reviewable</span>
                </div>
                <div className="stat-item">
                  <span className="stat-number">{stats.withAnswers}</span>
                  <span className="stat-label">With Answers</span>
                </div>
                <div className="stat-item">
                  <span className="stat-number">{stats.withoutAnswers}</span>
                  <span className="stat-label">Missing Answers</span>
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

              {/* Status Tabs */}
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
                message="No questions were extracted from this document."
                actionText="Back to Documents"
                onAction={handleBackToDocuments}
              />
            ) : processedQuestions.length === 0 ? (
              <EmptyState
                title="No questions match filters"
                message="No questions matched your search criteria."
                actionText="Clear Filters"
                onAction={handleClearFilters}
              />
            ) : (
              processedQuestions.map((q) => {
                const isExpanded = !!expandedCards[q.question_id];
                const isEditing = editingQuestionId === q.question_id;
                const answerMissing = isAnswerMissing(q.answer_text);
                const questionPreview = getQuestionPreview(q);
                
                return (
                  <div 
                    key={q.question_id} 
                    className={`question-review-card ${isExpanded ? 'expanded' : ''} ${isEditing ? 'card-editing' : ''}`}
                  >
                    {/* Header */}
                    <div 
                      className="question-card-header"
                      onClick={() => toggleCard(q.question_id)}
                    >
                      <div className="question-header-left">
                        <span className="question-number-title">
                          Question {q.question_number ?? '—'}{q.sub_question_label ? ` (${q.sub_question_label})` : ''}
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
                        {isExpanded && !isEditing && (
                          <button
                            className="card-edit-trigger-btn"
                            onClick={(e) => startEditQuestion(q, e)}
                          >
                            Edit
                          </button>
                        )}
                        <svg viewBox="0 0 24 24" className="chevron-icon" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                      </div>
                    </div>

                    {/* Collapsed Preview */}
                    {!isExpanded && questionPreview && (
                      <div className="question-preview-content">
                        {questionPreview}
                      </div>
                    )}

                    {/* Expanded Content */}
                    {isExpanded && (
                      <div className="question-card-body">
                        {editGeneralError && isEditing && (
                          <div className="edit-general-error alert-error">
                            {editGeneralError}
                          </div>
                        )}

                        {isEditing ? (
                          /* EDITING FORM INTERFACE */
                          <div className="edit-question-fields">
                            <div className="edit-field-row">
                              <div className="edit-input-wrapper">
                                <label className="field-label">Question Number <span className="req">*</span></label>
                                <input
                                  type="text"
                                  name="question_number"
                                  value={editForm.question_number}
                                  onChange={handleFormChange}
                                  className={`input-field ${editErrors.question_number ? 'input-error' : ''}`}
                                />
                                {editErrors.question_number && (
                                  <span className="field-error-text">{editErrors.question_number}</span>
                                )}
                              </div>

                              <div className="edit-input-wrapper">
                                <SearchableSelect
                                  label="Chapter Mapping"
                                  id={`edit-chapter-${q.question_id}`}
                                  name="chapter"
                                  placeholder="Search chapters..."
                                  options={chapterOptions}
                                  value={editForm.chapter}
                                  onChange={handleChapterDropdownChange}
                                  error={editErrors.chapter}
                                  onCreateOption={handleCreateChapterPrompt}
                                  required
                                />
                              </div>
                            </div>

                            <div className="edit-textarea-wrapper">
                              <label className="field-label">Question Text <span className="req">*</span></label>
                              <textarea
                                name="question_text"
                                value={editForm.question_text}
                                onChange={handleFormChange}
                                rows="6"
                                className={`textarea-field ${editErrors.question_text ? 'input-error' : ''}`}
                                placeholder="Enter plain question text"
                              />
                              {editErrors.question_text && (
                                <span className="field-error-text">{editErrors.question_text}</span>
                              )}
                            </div>

                            <div className="edit-textarea-wrapper">
                              <label className="field-label">Answer Text <span className="req">*</span></label>
                              <textarea
                                name="answer_text"
                                value={editForm.answer_text}
                                onChange={handleFormChange}
                                rows="6"
                                className={`textarea-field ${editErrors.answer_text ? 'input-error' : ''}`}
                                placeholder="Enter plain answer text"
                              />
                              {editErrors.answer_text && (
                                <span className="field-error-text">{editErrors.answer_text}</span>
                              )}
                            </div>

                            <div className="edit-actions-panel">
                              <Button
                                type="button"
                                variant="outline"
                                onClick={cancelEditQuestion}
                                disabled={isSaving}
                              >
                                Cancel
                              </Button>
                              <Button
                                type="button"
                                variant="primary"
                                onClick={(e) => saveEditQuestion(q.question_id, e)}
                                disabled={isSaving}
                              >
                                {isSaving ? 'Saving...' : 'Save'}
                              </Button>
                            </div>
                          </div>
                        ) : (
                          /* READ ONLY VIEW MODE */
                          <>
                            <div className="question-field-group">
                              <span className="question-field-label">Chapter</span>
                              <span className="metadata-value" style={{ fontWeight: 600 }}>
                                {q.chapter_name || 'Not Assigned'}
                              </span>
                            </div>

                            <div className="question-field-group">
                              <span className="question-field-label">Question</span>
                              {q.question_content && q.question_content.trim().length > 0 ? (
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

                            <div className="question-field-group">
                              <span className="question-field-label">Answer</span>
                              {answerMissing ? (
                                <div className="question-text-box warning-box">
                                  Answer not available
                                </div>
                              ) : q.answer_content && q.answer_content.trim().length > 0 ? (
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
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </section>
        </div>
      </section>

      {/* INLINE CHAPTER CREATION CONFIRMATION DIALOG MODAL */}
      {pendingChapterName && (
        <div className="modal-backdrop">
          <div className="modal-card inline-create-modal">
            <div className="modal-header">
              <h3>Create New Chapter</h3>
              <button className="close-modal-btn" onClick={() => setPendingChapterName('')}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <p>
                The chapter <strong>"{pendingChapterName}"</strong> does not exist in this subject. Would you like to create it?
              </p>
              {chapterCreationError && (
                <div className="alert-error" style={{ fontSize: '0.85rem', marginTop: '0.5rem', padding: '0.5rem' }}>
                  {chapterCreationError}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <Button
                type="button"
                variant="outline"
                onClick={() => setPendingChapterName('')}
                disabled={isCreatingChapter}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="primary"
                onClick={confirmCreateChapter}
                disabled={isCreatingChapter}
              >
                {isCreatingChapter ? 'Creating...' : 'Create'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Review;
