import api from './api';

/**
 * Service to handle question operations
 */
const questionService = {
  /**
   * Fetch all questions
   * @returns {Promise<Array>} List of questions
   */
  getQuestions: async (documentId) => {
    const response = await api.get('/questions/', {
      params: documentId ? { document_id: documentId } : {}
    });
    return response.data;
  },

  /**
   * Update an individual question
   * @param {number|string} questionId
   * @param {Object} data - fields to partially update
   * @returns {Promise<Object>} Updated question details
   */
  updateQuestion: async (questionId, data) => {
    const response = await api.patch(`/questions/${questionId}/`, data);
    return response.data;
  },
};

export default questionService;
