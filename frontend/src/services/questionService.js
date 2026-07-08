import api from './api';

/**
 * Service to handle question operations
 */
const questionService = {
  /**
   * Fetch all questions
   * @returns {Promise<Array>} List of questions
   */
  getQuestions: async () => {
    const response = await api.get('/questions/');
    return response.data;
  },
};

export default questionService;
