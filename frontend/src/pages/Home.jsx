import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import Badge from '../components/common/Badge';
import EmptyState from '../components/common/EmptyState';
import LoadingSpinner from '../components/common/LoadingSpinner';
import documentService from '../services/documentService';
import './Home.css';

/**
 * Landing Page displaying Test Series introduction and recent papers list
 */
const Home = () => {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch documents inside useEffect asynchronously to avoid synchronous effect states
  useEffect(() => {
    let active = true;

    const fetchDocuments = async () => {
      try {
        const data = await documentService.getDocuments();
        if (active) {
          setDocuments(data);
          setLoading(false);
        }
      } catch (err) {
        console.error('Error fetching documents:', err);
        if (active) {
          setError('Unable to load papers.');
          setLoading(false);
        }
      }
    };

    fetchDocuments();

    return () => {
      active = false;
    };
  }, []);

  const handleUploadClick = () => {
    navigate('/upload');
  };

  const handleReviewClick = (docId) => {
    navigate(`/review/${docId}`);
  };

  // Helper trigger to retry fetching documents on error state
  const handleRetry = () => {
    setLoading(true);
    setError(null);
    documentService.getDocuments()
      .then((data) => {
        setDocuments(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Retry fetch error:', err);
        setError('Unable to load papers.');
        setLoading(false);
      });
  };

  return (
    <div className="home-container container">
      {/* Hero Section */}
      <section className="home-hero">
        <h1 className="home-title">Test Series</h1>
        <p className="home-subtitle">
          Upload previous year papers, build your question bank, and generate practice papers.
        </p>
        <Button variant="secondary" onClick={handleUploadClick} className="home-hero-btn">
          Upload Paper
        </Button>
      </section>

      {/* Recent Papers List */}
      <section className="recent-papers-section">
        <h3 className="section-title">Recent Papers</h3>

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

        {!loading && !error && documents.length > 0 && (
          <div className="papers-grid">
            {documents.map((doc) => {
              // Combine attempt info
              const attemptLabel = doc.paper_session
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
                      <span className="detail-label">Type:</span>
                      <span className="detail-value">{doc.document_type}</span>
                    </div>
                    <div className="detail-row">
                      <span className="detail-label">Attempt:</span>
                      <span className="detail-value">{attemptLabel}</span>
                    </div>
                    {/* Subject field is omitted because it is not returned by the backend serializer */}
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
                      disabled={true}
                      tooltip="Delete is currently unavailable."
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
    </div>
  );
};

export default Home;
