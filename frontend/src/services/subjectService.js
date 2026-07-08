import api from './api';

/**
 * Service to handle syllabus subjects and chapters operations
 */
const subjectService = {
  /**
   * Fetch all active subjects
   * @returns {Promise<Array>} List of subjects
   */
  getSubjects: async () => {
    const response = await api.get('/subjects/');
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
};

export default subjectService;
