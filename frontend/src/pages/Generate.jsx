import { useState, useEffect, useRef, useCallback } from 'react';
import subjectService from '../services/subjectService';
import paperService from '../services/paperService';
import './Generate.css';

// ─── Constants ───────────────────────────────────────────────────────────────

const MODULES = [
  { value: 'RTP',  label: 'RTP',       desc: 'Revision Test Paper' },
  { value: 'PYQ',  label: 'PYQ',       desc: 'Previous Year Questions' },
  { value: 'MOCK', label: 'Mock Test', desc: 'Full Mock Test' },
];

const QUESTION_TYPES = [
  { value: '',           label: 'Mixed (no filter)' },
  { value: 'THEORY',     label: 'Theory' },
  { value: 'PRACTICAL',  label: 'Practical' },
  { value: 'CASE_STUDY', label: 'Case Study' },
  { value: 'MCQ',        label: 'MCQ' },
];

const EXAM_MONTHS = [
  '', 'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const DEBOUNCE_MS = 600;

// ─── Component ───────────────────────────────────────────────────────────────

const Generate = () => {
  // Filter state
  const [paperTitle, setPaperTitle]     = useState('');
  const [subjects, setSubjects]         = useState([]);
  const [selectedSubject, setSelectedSubject] = useState(null);
  const [module, setModule]             = useState('');
  const [chapters, setChapters]         = useState([]);
  const [selectedChapters, setSelectedChapters] = useState([]);
  const [chapterSearch, setChapterSearch] = useState('');
  const [totalMarks, setTotalMarks]     = useState('');
  const [questionCount, setQuestionCount] = useState('');
  const [questionType, setQuestionType] = useState('');
  const [yearFrom, setYearFrom]         = useState('');
  const [yearTo, setYearTo]             = useState('');
  const [examMonth, setExamMonth]       = useState('');

  // UI state
  const [subjectSearch, setSubjectSearch] = useState('');
  const [subjectOpen, setSubjectOpen]   = useState(false);
  const [subjectsLoading, setSubjectsLoading] = useState(true);
  const [chaptersLoading, setChaptersLoading] = useState(false);

  // Preview state
  const [preview, setPreview]           = useState(null);   // null = not run yet
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [rootQuestionIds, setRootQuestionIds] = useState([]);

  // Download state
  const [downloadingPaper, setDownloadingPaper]   = useState(false);
  const [downloadingAnswer, setDownloadingAnswer] = useState(false);
  const [downloadError, setDownloadError]         = useState(null);

  const debounceRef = useRef(null);
  const subjectDropdownRef = useRef(null);

  // ── Load subjects on mount ──────────────────────────────────────────────────
  useEffect(() => {
    subjectService.getSubjects()
      .then(data => setSubjects(data.filter(s => s.is_active !== false)))
      .catch(() => {})
      .finally(() => setSubjectsLoading(false));
  }, []);

  // ── Close subject dropdown on outside click ─────────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      if (subjectDropdownRef.current && !subjectDropdownRef.current.contains(e.target)) {
        setSubjectOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // ── Load chapters when subject + RTP selected ───────────────────────────────
  useEffect(() => {
    if (!selectedSubject || module !== 'RTP') {
      setChapters([]);
      setSelectedChapters([]);
      return;
    }
    setChaptersLoading(true);
    subjectService.getSubjectChapters(selectedSubject.subject_id)
      .then(data => setChapters(data))
      .catch(() => setChapters([]))
      .finally(() => setChaptersLoading(false));
  }, [selectedSubject, module]);

  // ── Reset selection whenever filters change ─────────────────────────────────
  const resetSelection = () => {
    setRootQuestionIds([]);
    setPreview(null);
    setPreviewError(null);
    setDownloadError(null);
  };

  // ── Build filter payload ────────────────────────────────────────────────────
  const buildFilters = useCallback(() => {
    if (!selectedSubject || !module) return null;
    const filters = {
      paper_title: paperTitle.trim() || 'Untitled Paper',
      subject_id: selectedSubject.subject_id,
      module,
    };
    if (module === 'RTP') {
      const count = parseInt(questionCount, 10);
      if (!count || count <= 0) return null;
      filters.question_count = count;
      if (selectedChapters.length > 0) {
        filters.chapter_ids = selectedChapters.map(c => c.chapter_id);
      }
    } else {
      const marks = parseInt(totalMarks, 10);
      if (!marks || marks <= 0) return null;
      filters.total_marks = marks;
    }
    if (questionType) filters.question_type = questionType;
    if (yearFrom) filters.year_from = parseInt(yearFrom, 10);
    if (yearTo)   filters.year_to   = parseInt(yearTo, 10);
    if (examMonth) filters.exam_month = examMonth;
    return filters;
  }, [
    paperTitle, selectedSubject, module, questionCount, selectedChapters,
    totalMarks, questionType, yearFrom, yearTo, examMonth,
  ]);

  // ── Debounced preview fetch ─────────────────────────────────────────────────
  useEffect(() => {
    resetSelection();
    clearTimeout(debounceRef.current);

    const filters = buildFilters();
    if (!filters) return;

    debounceRef.current = setTimeout(async () => {
      setPreviewLoading(true);
      setPreviewError(null);
      try {
        const data = await paperService.generatePreview(filters);
        setPreview(data);
        setRootQuestionIds(data.root_question_ids || []);
      } catch (err) {
        setPreviewError('Failed to load preview. Please check your filters and try again.');
      } finally {
        setPreviewLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(debounceRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperTitle, selectedSubject, module, questionCount, selectedChapters,
      totalMarks, questionType, yearFrom, yearTo, examMonth]);

  // ── Download handlers ───────────────────────────────────────────────────────
  const handleDownloadPaper = async () => {
    if (!rootQuestionIds.length) return;
    setDownloadingPaper(true);
    setDownloadError(null);
    try {
      await paperService.downloadQuestionPaper({
        paper_title: paperTitle.trim() || 'Untitled Paper',
        root_question_ids: rootQuestionIds,
      });
    } catch {
      setDownloadError('Failed to generate Question Paper. Please try again.');
    } finally {
      setDownloadingPaper(false);
    }
  };

  const handleDownloadAnswer = async () => {
    if (!rootQuestionIds.length) return;
    setDownloadingAnswer(true);
    setDownloadError(null);
    try {
      await paperService.downloadAnswerSheet({
        paper_title: paperTitle.trim() || 'Untitled Paper',
        root_question_ids: rootQuestionIds,
      });
    } catch {
      setDownloadError('Failed to generate Answer Sheet. Please try again.');
    } finally {
      setDownloadingAnswer(false);
    }
  };

  // ── Chapter multi-select helpers ────────────────────────────────────────────
  const toggleChapter = (chapter) => {
    setSelectedChapters(prev =>
      prev.some(c => c.chapter_id === chapter.chapter_id)
        ? prev.filter(c => c.chapter_id !== chapter.chapter_id)
        : [...prev, chapter]
    );
  };

  const filteredChapters = chapters.filter(c =>
    c.chapter_name.toLowerCase().includes(chapterSearch.toLowerCase())
  );

  const filteredSubjects = subjects.filter(s =>
    s.name.toLowerCase().includes(subjectSearch.toLowerCase()) ||
    s.exam_level.toLowerCase().includes(subjectSearch.toLowerCase())
  );

  // ── Derived UI flags ────────────────────────────────────────────────────────
  const canPreview = !!(selectedSubject && module && (
    (module === 'RTP' && questionCount > 0) ||
    (module !== 'RTP' && totalMarks > 0)
  ));
  const hasResults = preview && preview.available_questions > 0;
  const canDownload = rootQuestionIds.length > 0;

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="generate-page">
      {/* ── Left Panel: Filters ── */}
      <div className="generate-filters">
        <div className="generate-filters-header">
          <h1 className="generate-title">Generate Practice Paper</h1>
          <p className="generate-subtitle">Set your criteria and download a custom paper instantly.</p>
        </div>

        <div className="generate-form">

          {/* Paper Title */}
          <div className="form-group">
            <label className="form-label" htmlFor="paper-title">
              Paper Title <span className="required-star">*</span>
            </label>
            <input
              id="paper-title"
              type="text"
              className="form-input"
              placeholder="e.g. FR Chapter 5 Practice"
              value={paperTitle}
              onChange={e => setPaperTitle(e.target.value)}
              maxLength={100}
            />
            <span className="form-hint">{paperTitle.trim().length}/100 characters</span>
          </div>

          {/* Subject */}
          <div className="form-group" ref={subjectDropdownRef}>
            <label className="form-label">
              Subject <span className="required-star">*</span>
            </label>
            <div className="custom-select-wrapper">
              <button
                type="button"
                className={`custom-select-trigger ${subjectOpen ? 'open' : ''}`}
                onClick={() => setSubjectOpen(o => !o)}
                id="subject-select"
              >
                {selectedSubject
                  ? <><span className="select-value">{selectedSubject.name}</span><span className="select-badge">{selectedSubject.exam_level}</span></>
                  : <span className="select-placeholder">Select subject…</span>
                }
                <span className="select-arrow">▾</span>
              </button>
              {subjectOpen && (
                <div className="custom-select-dropdown">
                  <input
                    type="text"
                    className="dropdown-search"
                    placeholder="Search subjects…"
                    value={subjectSearch}
                    onChange={e => setSubjectSearch(e.target.value)}
                    autoFocus
                  />
                  <div className="dropdown-list">
                    {subjectsLoading && <div className="dropdown-empty">Loading…</div>}
                    {!subjectsLoading && filteredSubjects.length === 0 && (
                      <div className="dropdown-empty">No subjects found.</div>
                    )}
                    {filteredSubjects.map(s => (
                      <button
                        key={s.subject_id}
                        type="button"
                        className={`dropdown-item ${selectedSubject?.subject_id === s.subject_id ? 'selected' : ''}`}
                        onClick={() => {
                          setSelectedSubject(s);
                          setSubjectOpen(false);
                          setSubjectSearch('');
                          setModule('');
                        }}
                      >
                        <span className="dropdown-item-name">{s.name}</span>
                        <span className="dropdown-item-badge">{s.exam_level}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Module */}
          <div className="form-group">
            <label className="form-label">Module <span className="required-star">*</span></label>
            <div className="module-buttons">
              {MODULES.map(m => (
                <button
                  key={m.value}
                  type="button"
                  className={`module-btn ${module === m.value ? 'active' : ''}`}
                  onClick={() => { setModule(m.value); setSelectedChapters([]); }}
                  disabled={!selectedSubject}
                  title={m.desc}
                  id={`module-${m.value.toLowerCase()}`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Chapters (RTP only) */}
          {module === 'RTP' && selectedSubject && (
            <div className="form-group">
              <label className="form-label">Chapters <span className="form-optional">(optional)</span></label>
              {chaptersLoading && <div className="loading-hint">Loading chapters…</div>}
              {!chaptersLoading && chapters.length === 0 && (
                <div className="empty-chapters-msg">
                  No chapters available for this subject.
                </div>
              )}
              {!chaptersLoading && chapters.length > 0 && (
                <>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Search chapters…"
                    value={chapterSearch}
                    onChange={e => setChapterSearch(e.target.value)}
                    id="chapter-search"
                  />
                  <div className="chapter-list">
                    {filteredChapters.map(c => {
                      const checked = selectedChapters.some(sc => sc.chapter_id === c.chapter_id);
                      return (
                        <label key={c.chapter_id} className={`chapter-item ${checked ? 'checked' : ''}`}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleChapter(c)}
                            id={`chapter-${c.chapter_id}`}
                          />
                          <span>{c.chapter_name}</span>
                        </label>
                      );
                    })}
                  </div>
                  {selectedChapters.length > 0 && (
                    <div className="chapter-tags">
                      {selectedChapters.map(c => (
                        <span key={c.chapter_id} className="chapter-tag">
                          {c.chapter_name}
                          <button type="button" onClick={() => toggleChapter(c)} aria-label="Remove">×</button>
                        </span>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Constraint: Question Count (RTP) or Total Marks (PYQ/MOCK) */}
          {module === 'RTP' && (
            <div className="form-group">
              <label className="form-label" htmlFor="question-count">
                Number of Questions <span className="required-star">*</span>
              </label>
              <input
                id="question-count"
                type="number"
                className="form-input"
                min={1}
                placeholder="e.g. 15"
                value={questionCount}
                onChange={e => setQuestionCount(e.target.value)}
              />
            </div>
          )}
          {(module === 'PYQ' || module === 'MOCK') && (
            <div className="form-group">
              <label className="form-label" htmlFor="total-marks">
                Total Marks <span className="required-star">*</span>
              </label>
              <div className="marks-preset-row">
                {[50, 70, 100].map(m => (
                  <button
                    key={m}
                    type="button"
                    className={`marks-preset-btn ${totalMarks === String(m) ? 'active' : ''}`}
                    onClick={() => setTotalMarks(String(m))}
                    id={`marks-preset-${m}`}
                  >
                    {m} Marks
                  </button>
                ))}
              </div>
              <input
                id="total-marks"
                type="number"
                className="form-input"
                min={1}
                placeholder="Or enter custom marks…"
                value={totalMarks}
                onChange={e => setTotalMarks(e.target.value)}
              />
            </div>
          )}

          {/* Optional filters — collapsed section */}
          {module && (
            <details className="optional-filters" id="optional-filters">
              <summary className="optional-filters-summary">Optional Filters</summary>
              <div className="optional-filters-body">

                {/* Question Type */}
                <div className="form-group">
                  <label className="form-label" htmlFor="question-type">Question Type</label>
                  <select
                    id="question-type"
                    className="form-select"
                    value={questionType}
                    onChange={e => setQuestionType(e.target.value)}
                  >
                    {QUESTION_TYPES.map(t => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>

                {/* Year Range */}
                <div className="form-group">
                  <label className="form-label">Year Range</label>
                  <div className="year-range-row">
                    <input
                      type="number"
                      className="form-input"
                      placeholder="From"
                      min={2000}
                      max={2100}
                      value={yearFrom}
                      onChange={e => setYearFrom(e.target.value)}
                      id="year-from"
                    />
                    <span className="year-range-sep">–</span>
                    <input
                      type="number"
                      className="form-input"
                      placeholder="To"
                      min={2000}
                      max={2100}
                      value={yearTo}
                      onChange={e => setYearTo(e.target.value)}
                      id="year-to"
                    />
                  </div>
                </div>

                {/* Exam Month */}
                <div className="form-group">
                  <label className="form-label" htmlFor="exam-month">Exam Month</label>
                  <select
                    id="exam-month"
                    className="form-select"
                    value={examMonth}
                    onChange={e => setExamMonth(e.target.value)}
                  >
                    <option value="">Any month</option>
                    {EXAM_MONTHS.filter(Boolean).map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>

              </div>
            </details>
          )}
        </div>
      </div>

      {/* ── Right Panel: Preview ── */}
      <div className="generate-preview">
        <div className="preview-card">
          <h2 className="preview-heading">Paper Preview</h2>

          {/* Initial state */}
          {!canPreview && !previewLoading && (
            <div className="preview-idle">
              <div className="preview-idle-icon">📄</div>
              <p>Select a subject and module to preview available questions.</p>
            </div>
          )}

          {/* Loading */}
          {previewLoading && (
            <div className="preview-loading">
              <div className="preview-spinner" />
              <p>Checking available questions…</p>
            </div>
          )}

          {/* Error */}
          {previewError && !previewLoading && (
            <div className="preview-error-msg">{previewError}</div>
          )}

          {/* No results */}
          {!previewLoading && !previewError && preview && preview.available_questions === 0 && (
            <div className="preview-empty">
              <div className="preview-empty-icon">🔍</div>
              <p className="preview-empty-title">No questions match the selected filters.</p>
              <ul className="preview-empty-tips">
                <li>Remove chapter filters</li>
                <li>Increase the year range</li>
                <li>Select "Mixed" question type</li>
              </ul>
            </div>
          )}

          {/* Results */}
          {!previewLoading && !previewError && hasResults && (
            <>
              {/* Warning banner */}
              {preview.warning && (
                <div className="preview-warning" role="alert">
                  <span className="preview-warning-icon">⚠</span>
                  <span>{preview.warning}</span>
                </div>
              )}

              {/* Stats grid */}
              <div className="preview-stats">
                <div className="stats-section">
                  <p className="stats-section-label">Available</p>
                  <div className="stats-row">
                    <div className="stat-item">
                      <span className="stat-value">{preview.available_questions}</span>
                      <span className="stat-label">Questions</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-value">{preview.available_marks}</span>
                      <span className="stat-label">Marks</span>
                    </div>
                  </div>
                </div>

                <div className="stats-divider" />

                <div className="stats-section">
                  <p className="stats-section-label">This paper</p>
                  <div className="stats-row">
                    <div className="stat-item">
                      <span className="stat-value">{preview.selected_question_count}</span>
                      <span className="stat-label">Questions</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-value">{preview.selected_total_marks}</span>
                      <span className="stat-label">Marks</span>
                    </div>
                  </div>
                  {preview.selection_quality && (
                    <p className="stats-quality">
                      Selection quality: <strong>{preview.selection_quality}</strong> of requested marks
                    </p>
                  )}
                </div>
              </div>

              {/* Download error */}
              {downloadError && (
                <div className="preview-error-msg" role="alert">{downloadError}</div>
              )}

              {/* Download buttons */}
              <div className="download-buttons">
                <button
                  type="button"
                  className="download-btn download-btn-primary"
                  disabled={!canDownload || downloadingPaper}
                  onClick={handleDownloadPaper}
                  id="download-question-paper"
                >
                  {downloadingPaper ? (
                    <><span className="btn-spinner" />Generating…</>
                  ) : (
                    <><span className="btn-icon">⬇</span> Download Question Paper</>
                  )}
                </button>
                <button
                  type="button"
                  className="download-btn download-btn-secondary"
                  disabled={!canDownload || downloadingAnswer}
                  onClick={handleDownloadAnswer}
                  id="download-answer-sheet"
                >
                  {downloadingAnswer ? (
                    <><span className="btn-spinner" />Generating…</>
                  ) : (
                    <><span className="btn-icon">⬇</span> Download Answer Sheet</>
                  )}
                </button>
              </div>

              <p className="download-note">
                Both files contain the same {preview.selected_question_count} questions in the same order.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Generate;
