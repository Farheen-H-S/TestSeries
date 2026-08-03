import api from './api';

/**
 * Service to handle generated practice papers and paper generation.
 */
const paperService = {
  /**
   * Fetch all generated papers (legacy — kept for compatibility)
   */
  getGeneratedPapers: async () => {
    const response = await api.get('/generated-papers/');
    return response.data;
  },

  /**
   * Fetch mapping of questions inside generated papers (legacy — kept for compatibility)
   */
  getGeneratedPaperQuestions: async () => {
    const response = await api.get('/generated-paper-questions/');
    return response.data;
  },

  /**
   * Run the selection engine against the given filters.
   * Returns availability metadata + root_question_ids for the selected paper.
   *
   * @param {Object} filters - Generation filter payload
   * @returns {Promise<Object>} Preview metadata
   */
  generatePreview: async (filters) => {
    const response = await api.post('/generate/preview/', filters);
    return response.data;
  },

  /**
   * Download a generated question paper PDF.
   * Sends root_question_ids (pre-selected by preview) so no re-selection occurs.
   * Triggers browser download via a synthetic anchor click.
   *
   * @param {Object} payload - { paper_title, root_question_ids }
   */
  downloadQuestionPaper: async (payload) => {
    const response = await api.post('/generate/question-paper/', payload, {
      responseType: 'blob',
      timeout: 60000, // PDF generation can take a moment
    });

    const filename = _extractFilename(response, `${payload.paper_title}.pdf`);
    _triggerDownload(response.data, filename);
  },

  /**
   * Download a generated answer sheet PDF.
   * Uses the same root_question_ids as the question paper to guarantee sync.
   *
   * @param {Object} payload - { paper_title, root_question_ids }
   */
  downloadAnswerSheet: async (payload) => {
    const response = await api.post('/generate/answer-sheet/', payload, {
      responseType: 'blob',
      timeout: 60000,
    });

    const filename = _extractFilename(response, `${payload.paper_title}_Answer_Sheet.pdf`);
    _triggerDownload(response.data, filename);
  },
};

/**
 * Extract filename from Content-Disposition header, falling back to the default.
 */
function _extractFilename(response, fallback) {
  const disposition = response.headers['content-disposition'] || '';
  const match = disposition.match(/filename="?([^"]+)"?/);
  return match ? match[1] : fallback;
}

/**
 * Trigger a browser file download from a Blob.
 */
function _triggerDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export default paperService;
