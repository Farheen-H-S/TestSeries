import { useState, useEffect } from 'react';
import subjectService from '../services/subjectService';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import Input from '../components/common/Input';
import Select from '../components/common/Select';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import './Subjects.css';

const EXAM_LEVELS = [
  { value: 'Foundation', label: 'Foundation' },
  { value: 'Intermediate', label: 'Intermediate' },
  { value: 'Final', label: 'Final' },
];

const Subjects = () => {
  const [subjects, setSubjects] = useState([]);
  const [selectedLevel, setSelectedLevel] = useState('All');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Subject Modal States
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [editingSubject, setEditingSubject] = useState(null);
  const [subjectForm, setSubjectForm] = useState({ name: '', exam_level: '' });
  const [subjectFormErrors, setSubjectFormErrors] = useState({});

  // Deletion stats preview modal state
  const [deletingSubject, setDeletingSubject] = useState(null);
  const [deleteStats, setDeleteStats] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Manage Chapters drawer/modal state
  const [activeSubject, setActiveSubject] = useState(null);
  const [chapters, setChapters] = useState([]);
  const [chapterForm, setChapterForm] = useState({ name: '' });
  const [chapterError, setChapterError] = useState(null);
  const [editingChapter, setEditingChapter] = useState(null); // Chapter object for renaming
  const [editingChapterName, setEditingChapterName] = useState('');

  useEffect(() => {
    fetchSubjects();
  }, [selectedLevel]);

  const fetchSubjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const levelFilter = selectedLevel === 'All' ? null : selectedLevel;
      const data = await subjectService.getSubjects(levelFilter);
      setSubjects(data);
    } catch (err) {
      console.error('Error fetching subjects:', err);
      setError('Unable to load subjects.');
    } finally {
      setLoading(false);
    }
  };

  const handleLevelTabClick = (level) => {
    setSelectedLevel(level);
  };

  // --- Subject Create & Edit handlers ---

  const openAddModal = () => {
    setSubjectForm({ name: '', exam_level: '' });
    setSubjectFormErrors({});
    setIsAddOpen(true);
  };

  const openEditModal = (subject) => {
    setSubjectForm({ name: subject.name, exam_level: subject.exam_level });
    setSubjectFormErrors({});
    setEditingSubject(subject);
  };

  const handleSubjectFormChange = (e) => {
    const { name, value } = e.target;
    setSubjectForm((prev) => ({ ...prev, [name]: value }));
    if (subjectFormErrors[name]) {
      setSubjectFormErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  };

  const validateSubjectForm = () => {
    const errors = {};
    const normalizedName = subjectForm.name.trim().replace(/\s+/g, ' ');
    if (!normalizedName) {
      errors.name = 'Subject name is required.';
    }
    if (!subjectForm.exam_level) {
      errors.exam_level = 'Exam level is required.';
    }
    return errors;
  };

  const handleSubjectSubmit = async (e) => {
    e.preventDefault();
    const errors = validateSubjectForm();
    if (Object.keys(errors).length > 0) {
      setSubjectFormErrors(errors);
      return;
    }

    const normalizedName = subjectForm.name.trim().replace(/\s+/g, ' ');

    try {
      if (editingSubject) {
        await subjectService.updateSubject(editingSubject.subject_id, {
          name: normalizedName,
          exam_level: subjectForm.exam_level,
        });
        setEditingSubject(null);
      } else {
        await subjectService.createSubject({
          name: normalizedName,
          exam_level: subjectForm.exam_level,
        });
        setIsAddOpen(false);
      }
      fetchSubjects();
    } catch (err) {
      console.error('Error saving subject:', err);
      if (err.response && err.response.status === 400) {
        const fieldErrors = err.response.data;
        const formErrors = {};
        Object.keys(fieldErrors).forEach((key) => {
          formErrors[key] = Array.isArray(fieldErrors[key]) ? fieldErrors[key][0] : fieldErrors[key];
        });
        setSubjectFormErrors(formErrors);
      } else {
        setError('An unexpected error occurred while saving the subject.');
      }
    }
  };

  // --- Cascade Subject Deletion handlers ---

  const openDeleteModal = async (subject) => {
    setDeletingSubject(subject);
    setDeleteStats(null);
    try {
      const stats = await subjectService.getSubjectStats(subject.subject_id);
      setDeleteStats(stats);
    } catch (err) {
      console.error('Error fetching subject stats:', err);
      setError('Unable to load subject deletion preview stats.');
      setDeletingSubject(null);
    }
  };

  const handleSubjectDelete = async () => {
    if (!deletingSubject) return;
    setIsDeleting(true);
    try {
      await subjectService.deleteSubject(deletingSubject.subject_id);
      setDeletingSubject(null);
      setDeleteStats(null);
      fetchSubjects();
    } catch (err) {
      console.error('Error deleting subject:', err);
      setError('Failed to delete subject. Please try again.');
    } finally {
      setIsDeleting(false);
    }
  };

  // --- Chapter Management handlers ---

  const openManageChapters = async (subject) => {
    setActiveSubject(subject);
    setChapterError(null);
    setEditingChapter(null);
    setChapterForm({ name: '' });
    try {
      const list = await subjectService.getSubjectChapters(subject.subject_id);
      setChapters(list);
    } catch (err) {
      console.error('Error fetching chapters:', err);
      setChapterError('Unable to load chapters.');
    }
  };

  const handleChapterFormChange = (e) => {
    setChapterForm({ name: e.target.value });
    if (chapterError) setChapterError(null);
  };

  const handleChapterAdd = async (e) => {
    e.preventDefault();
    const normalizedName = chapterForm.name.trim().replace(/\s+/g, ' ');
    if (!normalizedName) {
      setChapterError('Chapter name is required.');
      return;
    }

    try {
      await subjectService.createChapter(activeSubject.subject_id, {
        chapter_name: normalizedName,
      });
      setChapterForm({ name: '' });
      // Refresh list
      const list = await subjectService.getSubjectChapters(activeSubject.subject_id);
      setChapters(list);
    } catch (err) {
      console.error('Error adding chapter:', err);
      if (err.response && err.response.status === 400) {
        setChapterError(err.response.data.chapter_name || err.response.data.detail || 'Duplicate chapter name.');
      } else {
        setChapterError('Failed to add chapter.');
      }
    }
  };

  const startRenameChapter = (chapter) => {
    setEditingChapter(chapter);
    setEditingChapterName(chapter.chapter_name);
    setChapterError(null);
  };

  const handleChapterRename = async (chapterId) => {
    const normalizedName = editingChapterName.trim().replace(/\s+/g, ' ');
    if (!normalizedName) {
      setChapterError('Chapter name cannot be blank.');
      return;
    }

    try {
      await subjectService.updateChapter(chapterId, {
        chapter_name: normalizedName,
      });
      setEditingChapter(null);
      // Refresh list
      const list = await subjectService.getSubjectChapters(activeSubject.subject_id);
      setChapters(list);
    } catch (err) {
      console.error('Error renaming chapter:', err);
      if (err.response && err.response.status === 400) {
        setChapterError(err.response.data.chapter_name || err.response.data.detail || 'Rename failed. Name may exist.');
      } else {
        setChapterError('Failed to rename chapter.');
      }
    }
  };

  const handleChapterDelete = async (chapterId) => {
    setChapterError(null);
    try {
      await subjectService.deleteChapter(chapterId);
      // Refresh list
      const list = await subjectService.getSubjectChapters(activeSubject.subject_id);
      setChapters(list);
      
      // Update local subject card count in the background
      setSubjects((prev) =>
        prev.map((sub) =>
          sub.subject_id === activeSubject.subject_id
            ? { ...sub, chapters_count: sub.chapters_count - 1 }
            : sub
        )
      );
    } catch (err) {
      console.error('Error deleting chapter:', err);
      if (err.response && err.response.status === 400) {
        setChapterError(err.response.data.detail || 'Cannot delete chapter.');
      } else {
        setChapterError('Failed to delete chapter.');
      }
    }
  };

  const handleMoveChapter = async (chapterId, direction) => {
    setChapterError(null);
    try {
      await subjectService.reorderChapter(chapterId, direction);
      // Refresh list
      const list = await subjectService.getSubjectChapters(activeSubject.subject_id);
      setChapters(list);
    } catch (err) {
      console.error('Error reordering chapter:', err);
      setChapterError('Failed to reorder chapter.');
    }
  };

  const formatCardDate = (subject) => {
    const createDate = new Date(subject.created_at);
    const updateDate = new Date(subject.updated_at);

    const options = { day: 'numeric', month: 'long', year: 'numeric' };
    const createStr = createDate.toLocaleDateString('en-GB', options);
    const updateStr = updateDate.toLocaleDateString('en-GB', options);

    // If updated_at is within a threshold of 5 seconds of created_at, treat as "Created"
    const diffInSeconds = Math.abs(updateDate - createDate) / 1000;
    if (diffInSeconds < 5) {
      return `Created ${createStr}`;
    }
    return `Last updated ${updateStr}`;
  };

  return (
    <div className="subjects-page-container container">
      {/* Header Section */}
      <section className="subjects-header">
        <div className="title-wrapper">
          <h2>Syllabus Management</h2>
          <p className="subtitle">Create and organize subjects and chapters for different exam levels.</p>
        </div>
        <Button variant="primary" onClick={openAddModal}>
          Add Subject
        </Button>
      </section>

      {/* Filter Tabs */}
      <div className="tabs-container">
        {['All', 'Foundation', 'Intermediate', 'Final'].map((level) => (
          <button
            key={level}
            className={`tab-btn ${selectedLevel === level ? 'tab-btn-active' : ''}`}
            onClick={() => handleLevelTabClick(level)}
          >
            {level}
          </button>
        ))}
      </div>

      {error && (
        <div className="subjects-alert alert-error">
          <span className="alert-message">{error}</span>
          <button className="close-alert-btn" onClick={() => setError(null)}>×</button>
        </div>
      )}

      {loading ? (
        <LoadingSpinner size="large" />
      ) : subjects.length === 0 ? (
        <EmptyState
          title="No subjects found."
          message={selectedLevel === 'All' ? "Add your first subject to start building the syllabus." : `No subjects found in ${selectedLevel} level.`}
          actionText={selectedLevel === 'All' ? "Add First Subject" : undefined}
          onAction={selectedLevel === 'All' ? openAddModal : undefined}
        />
      ) : (
        <div className="subjects-grid">
          {subjects.map((sub) => (
            <Card key={sub.subject_id} className="subject-card">
              <div className="subject-card-body">
                <span className="card-exam-level">{sub.exam_level}</span>
                <h4 className="card-subject-name">{sub.name}</h4>
                <div className="card-meta">
                  <span className="meta-chapters">{sub.chapters_count || 0} Chapters</span>
                  <span className="meta-date">{formatCardDate(sub)}</span>
                </div>
              </div>
              <div className="subject-card-actions">
                <button
                  type="button"
                  className="card-action-btn primary-action"
                  onClick={() => openManageChapters(sub)}
                >
                  Manage Chapters
                </button>
                <button
                  type="button"
                  className="card-action-btn secondary-action"
                  onClick={() => openEditModal(sub)}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="card-action-btn danger-action"
                  onClick={() => openDeleteModal(sub)}
                >
                  Delete
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* --- ADD / EDIT SUBJECT MODAL --- */}
      {(isAddOpen || editingSubject) && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>{editingSubject ? 'Edit Subject' : 'Add Subject'}</h3>
              <button
                className="close-modal-btn"
                onClick={() => {
                  setIsAddOpen(false);
                  setEditingSubject(null);
                }}
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleSubjectSubmit} noValidate>
              <div className="modal-body">
                <Input
                  label="Subject Name"
                  id="subject_name"
                  name="name"
                  placeholder="e.g. Advanced Auditing"
                  value={subjectForm.name}
                  onChange={handleSubjectFormChange}
                  error={subjectFormErrors.name}
                  required
                />
                <Select
                  label="Exam Level"
                  id="subject_exam_level"
                  name="exam_level"
                  placeholder="Select Exam Level"
                  options={EXAM_LEVELS}
                  value={subjectForm.exam_level}
                  onChange={handleSubjectFormChange}
                  error={subjectFormErrors.exam_level}
                  required
                />
              </div>
              <div className="modal-footer">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setIsAddOpen(false);
                    setEditingSubject(null);
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  {editingSubject ? 'Save Changes' : 'Create Subject'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --- DELETE CONFIRMATION MODAL WITH STATS PREVIEW --- */}
      {deletingSubject && (
        <div className="modal-backdrop">
          <div className="modal-card delete-modal-card">
            <div className="modal-header">
              <h3>Delete Subject</h3>
              <button className="close-modal-btn" onClick={() => setDeletingSubject(null)}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <p className="delete-warning-intro">
                You are about to delete <strong>{deletingSubject.name}</strong> ({deletingSubject.exam_level}).
              </p>
              {deleteStats ? (
                <div className="delete-stats-container">
                  <p className="delete-warning-item-title">This subject contains:</p>
                  <ul className="delete-stats-list">
                    <li>• <strong>{deleteStats.documents_count}</strong> uploaded documents</li>
                    <li>• <strong>{deleteStats.questions_count}</strong> extracted questions</li>
                    <li>• <strong>{deleteStats.chapters_count}</strong> chapters</li>
                  </ul>
                  <p className="delete-consequences-text">
                    Deleting this subject will permanently remove all associated data. This action cannot be undone.
                  </p>
                </div>
              ) : (
                <LoadingSpinner size="small" />
              )}
            </div>
            <div className="modal-footer">
              <Button type="button" variant="outline" onClick={() => setDeletingSubject(null)}>
                Cancel
              </Button>
              <Button
                type="button"
                variant="primary"
                className="btn-danger-confirm"
                onClick={handleSubjectDelete}
                disabled={isDeleting || !deleteStats}
              >
                {isDeleting ? 'Deleting...' : 'Delete Everything'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* --- MANAGE CHAPTERS MODAL --- */}
      {activeSubject && (
        <div className="modal-backdrop">
          <div className="modal-card manage-chapters-card">
            <div className="modal-header">
              <div>
                <h3>Manage Chapters</h3>
                <span className="chapters-subtitle">{activeSubject.name} - {activeSubject.exam_level}</span>
              </div>
              <button className="close-modal-btn" onClick={() => setActiveSubject(null)}>
                &times;
              </button>
            </div>

            <div className="modal-body">
              {chapterError && (
                <div className="chapters-alert alert-error">
                  <span className="alert-message">{chapterError}</span>
                  <button className="close-alert-btn" onClick={() => setChapterError(null)}>×</button>
                </div>
              )}

              {/* Add Chapter Form */}
              <form onSubmit={handleChapterAdd} className="add-chapter-form">
                <input
                  type="text"
                  placeholder="Enter new chapter name"
                  value={chapterForm.name}
                  onChange={handleChapterFormChange}
                  className="chapter-input-field"
                />
                <Button type="submit" variant="secondary" className="add-chapter-btn">
                  Add
                </Button>
              </form>

              {/* Chapters List */}
              <div className="chapters-list-wrapper">
                {chapters.length === 0 ? (
                  <p className="no-chapters-msg">No chapters created yet.</p>
                ) : (
                  <ul className="chapters-list-items">
                    {chapters.map((ch, idx) => (
                      <li key={ch.chapter_id} className="chapter-list-item">
                        {editingChapter && editingChapter.chapter_id === ch.chapter_id ? (
                          <div className="chapter-rename-wrapper">
                            <input
                              type="text"
                              value={editingChapterName}
                              onChange={(e) => setEditingChapterName(e.target.value)}
                              className="chapter-rename-input"
                              autoFocus
                            />
                            <button
                              type="button"
                              className="chapter-rename-action save-rename"
                              onClick={() => handleChapterRename(ch.chapter_id)}
                            >
                              Save
                            </button>
                            <button
                              type="button"
                              className="chapter-rename-action cancel-rename"
                              onClick={() => setEditingChapter(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <>
                            <div className="chapter-item-details">
                              <span className="chapter-number">{idx + 1}.</span>
                              <span className="chapter-name">{ch.chapter_name}</span>
                            </div>
                            <div className="chapter-item-actions">
                              {/* Reorder Arrows */}
                              <button
                                type="button"
                                className="arrow-btn"
                                onClick={() => handleMoveChapter(ch.chapter_id, 'up')}
                                disabled={idx === 0}
                                title="Move Chapter Up"
                              >
                                ▲
                              </button>
                              <button
                                type="button"
                                className="arrow-btn"
                                onClick={() => handleMoveChapter(ch.chapter_id, 'down')}
                                disabled={idx === chapters.length - 1}
                                title="Move Chapter Down"
                              >
                                ▼
                              </button>
                              {/* Edit & Delete */}
                              <button
                                type="button"
                                className="btn-icon rename-ch-btn"
                                onClick={() => startRenameChapter(ch)}
                                title="Rename Chapter"
                              >
                                Rename
                              </button>
                              <button
                                type="button"
                                className="btn-icon delete-ch-btn"
                                onClick={() => handleChapterDelete(ch.chapter_id)}
                                title="Delete Chapter"
                              >
                                Delete
                              </button>
                            </div>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Subjects;
