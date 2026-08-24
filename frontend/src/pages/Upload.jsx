import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Input from '../components/common/Input';
import Select from '../components/common/Select';
import SearchableSelect from '../components/common/SearchableSelect';
import Button from '../components/common/Button';
import LoadingSpinner from '../components/common/LoadingSpinner';
import documentService from '../services/documentService';
import subjectService from '../services/subjectService';
import { DOCUMENT_TYPES, EXAM_MONTHS } from '../constants/documentConstants';
import { formatFileSize, generateYearList } from '../utils/helpers';
import './Upload.css';

const Upload = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  
  const [formData, setFormData] = useState({
    subject: '', // Primary key of selected subject
    title: '',
    document_type: '',
    paper_year: '',
    exam_month: '',
  });

  const [subjects, setSubjects] = useState([]);
  const [subjectsLoading, setSubjectsLoading] = useState(true);
  const [file, setFile] = useState(null);
  const [errors, setErrors] = useState({});
  const [generalError, setGeneralError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const years = generateYearList();

  // Load subjects on page mount
  useEffect(() => {
    const loadSubjects = async () => {
      try {
        const data = await subjectService.getSubjects();
        setSubjects(data);
      } catch (err) {
        console.error('Error loading subjects:', err);
        setGeneralError('Failed to load subjects from backend.');
      } finally {
        setSubjectsLoading(false);
      }
    };
    loadSubjects();
  }, []);

  // Find resolved exam level from selected subject
  const selectedSubjectObj = subjects.find(
    (sub) => sub.subject_id === Number(formData.subject)
  );
  const resolvedExamLevel = selectedSubjectObj ? selectedSubjectObj.exam_level : '';

  // Field validation helper
  const validateField = (name, value) => {
    switch (name) {
      case 'subject':
        if (!value) return 'Subject is required.';
        return '';
      case 'document_type':
        if (!value) return 'Document type is required.';
        return '';
      case 'paper_year':
        if (!value) return 'Paper year is required.';
        return '';
      case 'exam_month':
        if (!value) return 'Exam month is required.';
        return '';
      default:
        return '';
    }
  };

  // Handle input changes
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    
    // Validate on the fly
    const fieldError = validateField(name, value);
    setErrors((prev) => {
      const nextErrors = { ...prev };
      if (fieldError) {
        nextErrors[name] = fieldError;
      } else {
        delete nextErrors[name];
      }
      return nextErrors;
    });
    
    if (generalError) setGeneralError(null);
  };

  // File handler with smart metadata auto-detection
  const handleFile = (selectedFile) => {
    if (!selectedFile) return;

    let fileError = '';
    const fileExt = selectedFile.name.split('.').pop().toLowerCase();
    if (selectedFile.type !== 'application/pdf' && fileExt !== 'pdf') {
      fileError = 'Only PDF files are allowed.';
    } else if (selectedFile.size > 100 * 1024 * 1024) {
      fileError = 'File size exceeds the limit of 100MB.';
    }

    setErrors((prev) => {
      const nextErrors = { ...prev };
      if (fileError) {
        nextErrors.file = fileError;
      } else {
        delete nextErrors.file;
      }
      return nextErrors;
    });

    setFile(selectedFile);
    if (generalError) setGeneralError(null);

    // Auto-detect Month, Year, Doc Type, Subject from filename if not already selected
    if (!fileError) {
      const nameLower = selectedFile.name.toLowerCase();
      setFormData((prev) => {
        const next = { ...prev };

        // 1. Detect Month
        if (/\b(jan|january)\b/i.test(nameLower)) next.exam_month = 'January';
        else if (/\b(feb|february)\b/i.test(nameLower)) next.exam_month = 'February';
        else if (/\b(mar|march)\b/i.test(nameLower)) next.exam_month = 'March';
        else if (/\b(apr|april)\b/i.test(nameLower)) next.exam_month = 'April';
        else if (/\b(may)\b/i.test(nameLower)) next.exam_month = 'May';
        else if (/\b(jun|june)\b/i.test(nameLower)) next.exam_month = 'June';
        else if (/\b(jul|july)\b/i.test(nameLower)) next.exam_month = 'July';
        else if (/\b(aug|august)\b/i.test(nameLower)) next.exam_month = 'August';
        else if (/\b(sep|sept|september)\b/i.test(nameLower)) next.exam_month = 'September';
        else if (/\b(oct|october)\b/i.test(nameLower)) next.exam_month = 'October';
        else if (/\b(nov|november)\b/i.test(nameLower)) next.exam_month = 'November';
        else if (/\b(dec|december)\b/i.test(nameLower)) next.exam_month = 'December';

        // 2. Detect Year
        const yearMatch = nameLower.match(/\b(20\d\d)\b/);
        if (yearMatch) next.paper_year = Number(yearMatch[1]);

        // 3. Detect Document Type
        if (/\brtp\b/i.test(nameLower)) next.document_type = 'RTP';
        else if (/\b(mtp|mock)\b/i.test(nameLower)) next.document_type = 'MOCK';
        else if (/\b(pyq|past)\b/i.test(nameLower)) next.document_type = 'PYQ';

        // 4. Detect Subject
        if (subjects && subjects.length > 0) {
          if (/\b(fr|financial\s*reporting)\b/i.test(nameLower)) {
            const frSub = subjects.find((s) => /financial\s*reporting/i.test(s.name) || /fr/i.test(s.code || ''));
            if (frSub) next.subject = frSub.subject_id;
          } else if (/\b(dt|direct\s*tax|direct\s*taxes)\b/i.test(nameLower)) {
            const dtSub = subjects.find((s) => /direct\s*tax/i.test(s.name) || /dt/i.test(s.code || ''));
            if (dtSub) next.subject = dtSub.subject_id;
          }
        }

        return next;
      });
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  // Drag and drop handlers
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isUploading) return;

    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragActive(true);
    } else if (e.type === 'dragleave') {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isUploading) return;
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleRemoveFile = () => {
    if (isUploading) return;
    setFile(null);
    setErrors((prev) => {
      const nextErrors = { ...prev };
      delete nextErrors.file;
      return nextErrors;
    });
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const triggerFileSelect = () => {
    if (isUploading) return;
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  // Check if form is completely valid
  const isFormValid =
    formData.subject &&
    formData.document_type &&
    formData.paper_year &&
    formData.exam_month &&
    file &&
    !errors.file;

  // Submit handler
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isUploading || !isFormValid) return;

    setIsUploading(true);
    setUploadProgress(0);
    setGeneralError(null);

    const submissionData = new FormData();
    submissionData.append('subject', Number(formData.subject));
    
    if (formData.title.trim()) {
      submissionData.append('title', formData.title.trim());
    }
    
    submissionData.append('document_type', formData.document_type);
    submissionData.append('paper_year', Number(formData.paper_year));
    submissionData.append('exam_month', formData.exam_month);
    submissionData.append('file', file);

    try {
      const progressCallback = (progressEvent) => {
        if (progressEvent.lengthComputable && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(Math.min(percent, 99));
        } else {
          setUploadProgress(null);
        }
      };

      const result = await documentService.uploadDocument(submissionData, progressCallback);
      setUploadProgress(100);
      
      // Navigate to processing page
      navigate(`/processing/${result.document_id}`);
    } catch (err) {
      setIsUploading(false);
      setUploadProgress(null);

      if (err.response && err.response.status === 400) {
        const backendErrors = err.response.data;
        const mappedErrors = {};
        Object.keys(backendErrors).forEach((key) => {
          mappedErrors[key] = Array.isArray(backendErrors[key])
            ? backendErrors[key][0]
            : backendErrors[key];
        });
        setErrors(mappedErrors);
      } else {
        setGeneralError(
          err.response?.data?.detail || 
          err.response?.data?.message || 
          err.message || 
          'Upload failed. Please verify the fields or try again.'
        );
      }
    }
  };

  // Handle empty state on subjects
  if (!subjectsLoading && subjects.length === 0) {
    return (
      <div className="upload-container container">
        <div className="upload-card empty-subjects-card">
          <h2 className="upload-title">Upload Question Paper</h2>
          <div className="empty-subjects-warning">
            <p>No subjects available in the database. You must create at least one subject in the syllabus first before you can upload papers.</p>
            <Button variant="primary" onClick={() => navigate('/subjects')}>
              Go to Subject Management
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Format options for SearchableSelect
  const subjectOptions = subjects.map((sub) => ({
    value: sub.subject_id,
    label: sub.name,
    sublabel: sub.exam_level,
  }));

  return (
    <div className="upload-container container">
      <div className="upload-card">
        <h2 className="upload-title">Upload Question Paper</h2>
        <p className="upload-subtitle">Provide details about the paper and upload the PDF file to begin extraction.</p>

        {generalError && (
          <div className="upload-alert alert-error">
            <span className="alert-message">{generalError}</span>
          </div>
        )}

        {subjectsLoading ? (
          <div className="subjects-loading-wrapper">
            <LoadingSpinner size="medium" />
            <p className="loading-text">Loading subjects...</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="upload-form" noValidate>
            <div className="form-grid">
              <SearchableSelect
                label="Subject"
                id="subject"
                name="subject"
                placeholder="Search subjects..."
                options={subjectOptions}
                value={formData.subject}
                onChange={handleInputChange}
                error={errors.subject}
                required
                disabled={isUploading}
              />

              <Input
                label="Exam Level"
                id="exam_level"
                name="exam_level"
                value={resolvedExamLevel}
                placeholder="Auto-resolved from subject"
                disabled
                readOnly
              />

              <Input
                label="Document Title"
                id="title"
                name="title"
                placeholder="e.g. FM Nov 2025 Paper (Optional)"
                value={formData.title}
                onChange={handleInputChange}
                error={errors.title}
                disabled={isUploading}
              />

              <Select
                label="Document Type"
                id="document_type"
                name="document_type"
                placeholder="Select Type"
                options={DOCUMENT_TYPES}
                value={formData.document_type}
                onChange={handleInputChange}
                error={errors.document_type}
                required
                disabled={isUploading}
              />

              <Select
                label="Paper Year"
                id="paper_year"
                name="paper_year"
                placeholder="Select Year"
                options={years}
                value={formData.paper_year}
                onChange={handleInputChange}
                error={errors.paper_year}
                required
                disabled={isUploading}
              />

              <Select
                label="Exam Month"
                id="exam_month"
                name="exam_month"
                placeholder="Select Month"
                options={EXAM_MONTHS}
                value={formData.exam_month}
                onChange={handleInputChange}
                error={errors.exam_month}
                required
                disabled={isUploading}
              />
            </div>

            {/* Drag & Drop File Zone */}
            <div className="file-upload-section">
              <label className="input-label">
                PDF Document <span className="input-required">*</span>
              </label>
              
              <div
                className={`dropzone ${isDragActive ? 'dropzone-active' : ''} ${
                  errors.file ? 'dropzone-error' : ''
                } ${isUploading ? 'dropzone-disabled' : ''}`}
                onDragEnter={handleDrag}
                onDragOver={handleDrag}
                onDragLeave={handleDrag}
                onDrop={handleDrop}
                onClick={triggerFileSelect}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  accept="application/pdf"
                  className="file-input-hidden"
                  disabled={isUploading}
                />

                <div className="dropzone-content">
                  <svg
                    className="upload-icon"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                    />
                  </svg>
                  {file ? (
                    <div className="selected-file-info" onClick={(e) => e.stopPropagation()}>
                      <span className="file-name" title={file.name}>
                        {file.name}
                      </span>
                      <span className="file-size">{formatFileSize(file.size)}</span>
                      {!isUploading && (
                        <button
                          type="button"
                          onClick={handleRemoveFile}
                          className="remove-file-btn"
                          aria-label="Remove file"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  ) : (
                    <>
                      <p className="dropzone-text">
                        Drag & Drop your PDF here, or <span className="browse-link">browse</span>
                      </p>
                      <p className="dropzone-subtext">PDF only (Max 100MB)</p>
                    </>
                  )}
                </div>
              </div>
              {errors.file && <span className="field-error-msg">{errors.file}</span>}
            </div>

            {/* Progress Bar / Submission States */}
            {isUploading && (
              <div className="upload-progress-container">
                {uploadProgress !== null ? (
                  <div className="progress-bar-wrapper">
                    <div className="progress-info">
                      <span className="progress-status-text">
                        Uploading paper...
                      </span>
                      <span className="progress-percentage">{uploadProgress}%</span>
                    </div>
                    <div className="progress-bar-track">
                      <div
                        className="progress-bar-fill"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="indeterminate-loader">
                    <div className="pulse-loader" />
                    <span className="progress-status-text">
                      Uploading paper...
                    </span>
                  </div>
                )}
              </div>
            )}

            <div className="form-actions">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate('/')}
                disabled={isUploading}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={isUploading || !isFormValid}
              >
                {isUploading ? 'Uploading...' : 'Upload & Process'}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default Upload;
