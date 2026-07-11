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
};

export default questionService;
