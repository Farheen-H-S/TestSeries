import api from './api';

/**
 * Service to handle generated practice papers
 */
const paperService = {
  /**
   * Fetch all generated papers
   * @returns {Promise<Array>} List of generated papers
   */
  getGeneratedPapers: async () => {
    const response = await api.get('/generated-papers/');
    return response.data;
  },

  /**
   * Fetch mapping of questions inside generated papers
   * @returns {Promise<Array>} List of generated paper question mappings
   */
  getGeneratedPaperQuestions: async () => {
    const response = await api.get('/generated-paper-questions/');
    return response.data;
  },
};

export default paperService;
