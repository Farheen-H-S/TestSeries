import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import documentService from '../services/documentService';
import subjectService from '../services/subjectService';
import { DOCUMENT_TYPES, EXAM_MONTHS } from '../constants/documentConstants';
import './Home.css';

/**
 * Landing Page displaying Test Series introduction, search & filter controls, and recent papers list
 */
const Home = () => {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSubject, setSelectedSubject] = useState('all');
  const [selectedMonth, setSelectedMonth] = useState('all');
  const [selectedYear, setSelectedYear] = useState('all');
  const [selectedType, setSelectedType] = useState('all');

  // Deletion double-confirmation modal state
  const [deletingDoc, setDeletingDoc] = useState(null);
  const [deleteStats, setDeleteStats] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  // Fetch documents and active subjects on mount
  useEffect(() => {
    let active = true;

    const fetchData = async () => {
      try {
        const [docsData, subjectsData] = await Promise.all([
          documentService.getDocuments(),
          subjectService.getSubjects().catch(() => []),
        ]);
        if (active) {
          setDocuments(docsData);
          setSubjects(subjectsData);
          setLoading(false);
        }
      } catch (err) {
        console.error('Error fetching data for Home page:', err);
        if (active) {
          setError('Unable to load papers.');
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      active = false;
    };
  }, []);

  // Compute available unique years from documents list
  const availableYears = useMemo(() => {
    const yearsSet = new Set(documents.map((d) => d.paper_year).filter(Boolean));
    return Array.from(yearsSet).sort((a, b) => b - a);
  }, [documents]);

  // Compute filtered documents dynamically
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      // 1. Search Query Filter (Title or Subject Name)
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const titleMatch = doc.title?.toLowerCase().includes(query);
        const subjectMatch = doc.subject?.name?.toLowerCase().includes(query);
        if (!titleMatch && !subjectMatch) return false;
      }
      // 2. Subject Filter
      if (selectedSubject !== 'all') {
        if (String(doc.subject?.subject_id) !== String(selectedSubject)) return false;
      }
      // 3. Month Filter
      if (selectedMonth !== 'all') {
        if (doc.exam_month?.toLowerCase() !== selectedMonth.toLowerCase()) return false;
      }
      // 4. Year Filter
      if (selectedYear !== 'all') {
        if (String(doc.paper_year) !== String(selectedYear)) return false;
      }
      // 5. Document Type Filter
      if (selectedType !== 'all') {
        if (doc.document_type?.toLowerCase() !== selectedType.toLowerCase()) return false;
      }
      return true;
    });
  }, [documents, searchQuery, selectedSubject, selectedMonth, selectedYear, selectedType]);

  const hasActiveFilters = Boolean(
    searchQuery.trim() ||
    selectedSubject !== 'all' ||
    selectedMonth !== 'all' ||
    selectedYear !== 'all' ||
    selectedType !== 'all'
  );

  const handleClearFilters = () => {
    setSearchQuery('');
    setSelectedSubject('all');
    setSelectedMonth('all');
    setSelectedYear('all');
    setSelectedType('all');
  };

  const handleUploadClick = () => {
    navigate('/upload');
  };

  const handleReviewClick = (docId) => {
    navigate(`/review/${docId}`);
  };

  // Open double-confirmation delete modal & fetch live impact stats
  const openDeleteModal = async (doc) => {
    setDeletingDoc(doc);
    setDeleteStats(null);
    setDeleteError(null);
    try {
      const stats = await documentService.getDocumentStats(doc.document_id);
      setDeleteStats(stats);
    } catch (err) {
      console.error('Failed to fetch document stats:', err);
      setDeleteStats({ questions_count: 0, logs_count: 0 });
    }
  };

  // Confirm paper deletion
  const handleConfirmDelete = async () => {
    if (!deletingDoc) return;

    setIsDeleting(true);
    setDeleteError(null);
    try {
      await documentService.deleteDocument(deletingDoc.document_id);
      setDocuments((prev) => prev.filter((d) => d.document_id !== deletingDoc.document_id));
      setDeletingDoc(null);
    } catch (err) {
      console.error('Error deleting document:', err);
      setDeleteError(err.response?.data?.detail || 'Failed to delete paper. Please try again.');
    } finally {
      setIsDeleting(false);
    }
  };

  // Helper trigger to retry fetching documents on error state
  const handleRetry = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      documentService.getDocuments(),
      subjectService.getSubjects().catch(() => []),
    ])
      .then(([docsData, subjectsData]) => {
        setDocuments(docsData);
        setSubjects(subjectsData);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Retry fetch error:', err);
        setError('Unable to load papers.');
        setLoading(false);
      });
  };

  const hasSubjects = subjects.length > 0;
  const hasDocuments = documents.length > 0;

  return (
    <div className="home-container container">
      {/* Hero Section */}
      <section className="home-hero">
        <h1 className="home-title">Test Series</h1>
        <p className="home-subtitle">
          Upload previous year papers, build your question bank, and generate practice papers.
        </p>
        <div className="home-hero-actions">
          <Button
            variant={!hasSubjects ? 'primary' : 'outline'}
            onClick={() => navigate('/subjects')}
            className="home-hero-btn"
          >
            Manage Subjects
          </Button>
          <Button
            variant={hasSubjects && !hasDocuments ? 'primary' : 'outline'}
            disabled={!hasSubjects}
            tooltip={!hasSubjects ? 'Add at least one subject first before uploading papers' : undefined}
            onClick={handleUploadClick}
            className="home-hero-btn"
          >
            Upload Paper
          </Button>
          <Button
            variant={hasSubjects && hasDocuments ? 'primary' : 'outline'}
            disabled={!hasDocuments}
            tooltip={!hasDocuments ? 'Upload and extract at least one paper before generating practice tests' : undefined}
            onClick={() => navigate('/generate')}
            className="home-hero-btn"
          >
            Generate Practice Paper
          </Button>
        </div>
      </section>

      {/* Recent Papers Section with Search & Filtering */}
      <section className="recent-papers-section">
        <div className="section-header-row">
          <h3 className="section-title">Recent Papers</h3>
          {documents.length > 0 && (
            <span className="total-papers-badge">
              {filteredDocuments.length} {filteredDocuments.length === 1 ? 'paper' : 'papers'}
            </span>
          )}
        </div>

        {/* Search & Filter Toolbar */}
        {!loading && !error && documents.length > 0 && (
          <div className="papers-filter-toolbar">
            <div className="filter-controls-row">
              {/* Search Bar Input */}
              <div className="search-input-wrapper">
                <svg className="search-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search papers by title or subject..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {searchQuery && (
                  <button
                    type="button"
                    className="clear-search-btn"
                    onClick={() => setSearchQuery('')}
                    title="Clear search"
                  >
                    &times;
                  </button>
                )}
              </div>

              {/* Filter Select Dropdowns */}
              <div className="filter-dropdowns">
                <select
                  className="filter-select"
                  value={selectedSubject}
                  onChange={(e) => setSelectedSubject(e.target.value)}
                  aria-label="Filter by Subject"
                >
                  <option value="all">All Subjects</option>
                  {subjects.map((sub) => (
                    <option key={sub.subject_id} value={sub.subject_id}>
                      {sub.name} ({sub.exam_level})
                    </option>
                  ))}
                </select>

                <select
                  className="filter-select"
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value)}
                  aria-label="Filter by Type"
                >
                  <option value="all">All Types</option>
                  {DOCUMENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>

                <select
                  className="filter-select"
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(e.target.value)}
                  aria-label="Filter by Month"
                >
                  <option value="all">All Months</option>
                  {EXAM_MONTHS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>

                <select
                  className="filter-select"
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(e.target.value)}
                  aria-label="Filter by Year"
                >
                  <option value="all">All Years</option>
                  {availableYears.map((year) => (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Active Filter Indicators & Clear Action */}
            {hasActiveFilters && (
              <div className="active-filters-bar">
                <span className="results-count">
                  Showing <strong>{filteredDocuments.length}</strong> of <strong>{documents.length}</strong> papers
                </span>
                <div className="filter-pills">
                  {searchQuery.trim() && (
                    <span className="filter-pill">
                      Title: "{searchQuery}"
                      <button onClick={() => setSearchQuery('')} aria-label="Clear title search">&times;</button>
                    </span>
                  )}
                  {selectedSubject !== 'all' && (
                    <span className="filter-pill">
                      Subject: {subjects.find((s) => String(s.subject_id) === String(selectedSubject))?.name || 'Selected'}
                      <button onClick={() => setSelectedSubject('all')} aria-label="Clear subject filter">&times;</button>
                    </span>
                  )}
                  {selectedType !== 'all' && (
                    <span className="filter-pill">
                      Type: {selectedType}
                      <button onClick={() => setSelectedType('all')} aria-label="Clear type filter">&times;</button>
                    </span>
                  )}
                  {selectedMonth !== 'all' && (
                    <span className="filter-pill">
                      Month: {selectedMonth}
                      <button onClick={() => setSelectedMonth('all')} aria-label="Clear month filter">&times;</button>
                    </span>
                  )}
                  {selectedYear !== 'all' && (
                    <span className="filter-pill">
                      Year: {selectedYear}
                      <button onClick={() => setSelectedYear('all')} aria-label="Clear year filter">&times;</button>
                    </span>
                  )}
                  <button type="button" className="clear-all-link" onClick={handleClearFilters}>
                    Clear All Filters
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {loading && <LoadingSpinner size="large" />}

        {error && (
          <div className="home-error-state">
            <p className="error-message">{error}</p>
            <Button variant="outline" onClick={handleRetry} className="retry-btn">
              Retry
            </Button>
          </div>
        )}

        {!loading && !error && documents.length === 0 && (
          <EmptyState
            title="No papers uploaded yet."
            message="Upload your first paper to begin building your question bank."
            actionText="Upload Your First Paper"
            onAction={handleUploadClick}
          />
        )}

        {!loading && !error && documents.length > 0 && filteredDocuments.length === 0 && (
          <EmptyState
            title="No matching papers found"
            message="No papers match your search and filter criteria. Try adjusting or clearing your filters."
            actionText="Clear Filters"
            onAction={handleClearFilters}
          />
        )}

        {!loading && !error && filteredDocuments.length > 0 && (
          <div className="papers-grid">
            {filteredDocuments.map((doc) => {
              const attemptLabel = doc.exam_month
                ? `${doc.exam_month} ${doc.paper_year}`
                : doc.paper_session
                  ? `${doc.paper_session} ${doc.paper_year}`
                  : `${doc.paper_year}`;

              return (
                <Card key={doc.document_id} className="paper-card">
                  <div className="paper-card-header">
                    <h4 className="paper-title" title={doc.title}>
                      {doc.title}
                    </h4>
                    <Badge status={doc.extraction_status} />
                  </div>

                  <div className="paper-card-details">
                    <div className="detail-row">
                      <span className="detail-label">Subject:</span>
                      <span className="detail-value">{doc.subject?.name || 'N/A'}</span>
                    </div>
                    <div className="detail-row">
                      <span className="detail-label">Type:</span>
                      <span className="detail-value">{doc.document_type}</span>
                    </div>
                    <div className="detail-row">
                      <span className="detail-label">Attempt:</span>
                      <span className="detail-value">{attemptLabel}</span>
                    </div>
                  </div>

                  <div className="paper-card-actions">
                    <Button
                      variant="primary"
                      onClick={() => handleReviewClick(doc.document_id)}
                      className="action-btn"
                    >
                      Open Review
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => openDeleteModal(doc)}
                      className="action-btn delete-btn"
                    >
                      Delete
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {/* Double-Confirmation Delete Paper Modal */}
      {deletingDoc && (
        <div className="modal-backdrop">
          <div className="modal-card delete-modal-card">
            <div className="modal-header">
              <h3>Delete Paper</h3>
              <button
                className="close-modal-btn"
                onClick={() => setDeletingDoc(null)}
                disabled={isDeleting}
              >
                &times;
              </button>
            </div>
            <div className="modal-body">
              <p className="delete-warning-intro">
                Are you sure you want to delete <strong>{deletingDoc.title}</strong>?
              </p>

              {deleteError && <div className="modal-error-message">{deleteError}</div>}

              {deleteStats ? (
                <div className="delete-stats-container">
                  <p className="delete-warning-item-title">This action will permanently remove:</p>
                  <ul className="delete-stats-list">
                    <li>• <strong>{deleteStats.questions_count}</strong> extracted questions</li>
                    <li>• Original PDF file and extraction logs</li>
                  </ul>
                  <p className="delete-consequences-text">
                    All extracted questions from this paper will be deleted and removed from practice tests. This action cannot be undone.
                  </p>
                </div>
              ) : (
                <LoadingSpinner size="small" />
              )}
            </div>
            <div className="modal-footer">
              <Button
                type="button"
                variant="outline"
                onClick={() => setDeletingDoc(null)}
                disabled={isDeleting}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="primary"
                className="btn-danger-confirm"
                onClick={handleConfirmDelete}
                disabled={isDeleting || !deleteStats}
              >
                {isDeleting ? 'Deleting...' : 'Delete Paper'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Home;
