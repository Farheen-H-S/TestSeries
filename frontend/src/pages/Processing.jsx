import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import documentService from '../services/documentService';
import './Processing.css';

const Processing = () => {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [logs, setLogs] = useState([]);
  const [pollingActive, setPollingActive] = useState(true);
  const consoleEndRef = useRef(null);

  const fetchStatusAndLogs = async () => {
    try {
      const docData = await documentService.getDocument(documentId);
      setDocument(docData);

      const logData = await documentService.getExtractionLogs(documentId);
      setLogs(logData);

      const currentStatus = docData.extraction_status;

      if (currentStatus === 'COMPLETED') {
        setPollingActive(false);
        // Wait for a brief moment for the user to see the completed state
        setTimeout(() => {
          navigate(`/review/${documentId}`);
        }, 1500);
      } else if (currentStatus === 'FAILED') {
        setPollingActive(false);
      }
    } catch (err) {
      console.error('Error polling status:', err);
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchStatusAndLogs();

    if (!pollingActive) return;

    const interval = setInterval(() => {
      fetchStatusAndLogs();
    }, 2000);

    return () => clearInterval(interval);
  }, [documentId, pollingActive]);

  useEffect(() => {
    // Auto scroll the console log to the bottom
    if (consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  if (!document) {
    return (
      <div className="processing-container container">
        <div className="processing-card loading-card">
          <div className="spinner"></div>
          <p>Loading document details...</p>
        </div>
      </div>
    );
  }

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'COMPLETED': return 'status-completed';
      case 'PROCESSING': return 'status-processing';
      case 'FAILED': return 'status-failed';
      default: return 'status-pending';
    }
  };

  const getStatusLabel = (status) => {
    switch (status) {
      case 'COMPLETED': return 'Completed';
      case 'PROCESSING': return 'Processing';
      case 'FAILED': return 'Extraction Failed';
      default: return 'Pending Queue';
    }
  };

  // Determine stage flags for visual indicators
  const isPending = document.extraction_status === 'PENDING';
  const isProcessing = document.extraction_status === 'PROCESSING';
  const isCompleted = document.extraction_status === 'COMPLETED';
  const isFailed = document.extraction_status === 'FAILED';

  return (
    <div className="processing-container container">
      <div className="processing-card">
        {/* Document Header Info */}
        <div className="doc-header">
          <div className="doc-meta-main">
            <span className="doc-type-badge">{document.document_type}</span>
            <h2 className="doc-title">{document.title}</h2>
          </div>
          <div className="doc-meta-sub">
            <p><strong>Subject:</strong> {document.subject?.name} ({document.subject?.exam_level})</p>
            <p><strong>Year/Session:</strong> {document.paper_year} {document.paper_session || ''}</p>
          </div>
        </div>

        {/* Visual Progress Status */}
        <div className="status-showcase">
          <div className="loader-area">
            {(isPending || isProcessing) && (
              <div className="spinner-glow">
                <div className="spinner-inner"></div>
              </div>
            )}
            {isCompleted && (
              <div className="success-icon-pulse">
                <svg viewBox="0 0 24 24" className="success-svg">
                  <path fill="none" stroke="currentColor" strokeWidth="3" d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
            )}
            {isFailed && (
              <div className="failed-icon-pulse">
                <svg viewBox="0 0 24 24" className="failed-svg">
                  <path fill="none" stroke="currentColor" strokeWidth="3" d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
            )}
          </div>
          <div className="status-label-group">
            <div className={`status-badge ${getStatusBadgeClass(document.extraction_status)}`}>
              {getStatusLabel(document.extraction_status)}
            </div>
            <p className="status-description">
              {isPending && "Waiting in queue for processing worker..."}
              {isProcessing && "Extracting questions, answers, marks, and mapping chapters..."}
              {isCompleted && "Successfully extracted all questions! Redirecting to review..."}
              {isFailed && "Document extraction halted due to parsing error."}
            </p>
          </div>
        </div>

        {/* Progress Pipeline Steps */}
        <div className="pipeline-steps">
          <div className={`step-item completed`}>
            <div className="step-bullet">✓</div>
            <div className="step-label">Upload Completed</div>
          </div>
          <div className={`step-item ${(!isPending) ? 'completed' : 'active'}`}>
            <div className="step-bullet">
              {isPending ? '⏳' : '✓'}
            </div>
            <div className="step-label">Queueing task</div>
          </div>
          <div className={`step-item ${(isCompleted || isFailed) ? 'completed' : (isProcessing ? 'active' : '')}`}>
            <div className="step-bullet">
              {(isCompleted || isFailed) ? '✓' : (isProcessing ? '⚡' : '○')}
            </div>
            <div className="step-label">Layout Analysis & Splitting</div>
          </div>
          <div className={`step-item ${isCompleted ? 'completed' : (isFailed ? 'failed' : '')}`}>
            <div className="step-bullet">
              {isCompleted ? '✓' : (isFailed ? '✗' : '○')}
            </div>
            <div className="step-label">Data Extraction & Persistence</div>
          </div>
        </div>

        {/* Live Logger Console */}
        <div className="console-log-section">
          <div className="console-log-header">
            <span className="console-title">Live Extraction logs</span>
            <span className="console-pulse">● Live</span>
          </div>
          <div className="console-log-body">
            {logs.length === 0 ? (
              <p className="console-line-info">Waiting for logs...</p>
            ) : (
              logs.slice().reverse().map((log) => (
                <div key={log.log_id} className={`console-line ${log.status.toLowerCase()}`}>
                  <span className="console-time">[{new Date(log.created_at).toLocaleTimeString()}]</span>
                  <span className="console-status-label">{log.status}:</span>
                  <span className="console-msg">{log.message || "Initializing extraction environment..."}</span>
                </div>
              ))
            )}
            <div ref={consoleEndRef} />
          </div>
        </div>

        {/* Actions (Only on fail) */}
        {isFailed && (
          <div className="action-buttons">
            <Link to="/upload" className="btn btn-primary">
              Back to Upload
            </Link>
          </div>
        )}
      </div>
    </div>
  );
};

export default Processing;
