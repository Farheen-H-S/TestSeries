import api from './api';

/**
 * Service to handle syllabus subjects and chapters operations
 */
const subjectService = {
  /**
   * Fetch all active subjects
   * @param {string} [examLevel] - Optional filter by exam level
   * @returns {Promise<Array>} List of subjects
   */
  getSubjects: async (examLevel) => {
    const params = examLevel ? { exam_level: examLevel } : {};
    const response = await api.get('/subjects/', { params });
    return response.data;
  },

  /**
   * Create a new subject
   */
  createSubject: async (data) => {
    const response = await api.post('/subjects/', data);
    return response.data;
  },

  /**
   * Get subject details by ID
   */
  getSubjectDetail: async (id) => {
    const response = await api.get(`/subjects/${id}/`);
    return response.data;
  },

  /**
   * Get subject deletion stats/warnings by ID
   */
  getSubjectStats: async (id) => {
    const response = await api.get(`/subjects/${id}/stats/`);
    return response.data;
  },

  /**
   * Update subject details (patch)
   */
  updateSubject: async (id, data) => {
    const response = await api.patch(`/subjects/${id}/`, data);
    return response.data;
  },

  /**
   * Delete a subject (cascade delete everything)
   */
  deleteSubject: async (id) => {
    const response = await api.delete(`/subjects/${id}/`);
    return response.data;
  },

  /**
   * Fetch chapters for a given subject ID
   * @param {number|string} subjectId - The primary key of the subject
   * @returns {Promise<Array>} List of chapters ordered by chapter_order
   */
  getSubjectChapters: async (subjectId) => {
    const response = await api.get(`/subjects/${subjectId}/chapters/`);
    return response.data;
  },

  /**
   * Create a chapter under a specific subject
   */
  createChapter: async (subjectId, data) => {
    const response = await api.post(`/subjects/${subjectId}/chapters/`, data);
    return response.data;
  },

  /**
   * Update (rename) a specific chapter
   */
  updateChapter: async (chapterId, data) => {
    const response = await api.patch(`/chapters/${chapterId}/`, data);
    return response.data;
  },

  /**
   * Reorder a chapter (POST /chapters/{chapterId}/reorder/ with direction)
   */
  reorderChapter: async (chapterId, direction) => {
    const response = await api.post(`/chapters/${chapterId}/reorder/`, { direction });
    return response.data;
  },

  /**
   * Delete a chapter individually
   */
  deleteChapter: async (chapterId) => {
    const response = await api.delete(`/chapters/${chapterId}/`);
    return response.data;
  },
};

export default subjectService;
