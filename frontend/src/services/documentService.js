import api from './api';

/**
 * Service to handle document/paper operations with Django backend
 */
const documentService = {
  /**
   * Fetch all documents from the backend
   * @returns {Promise<Array>} List of document items
   */
  getDocuments: async (params = {}) => {
    const response = await api.get('/documents/', { params });
    return response.data;
  },

  /**
   * Upload a new question paper PDF
   * @param {FormData} formData - Multipart data containing metadata and file
   * @returns {Promise<Object>} Uploaded document metadata
   */
  uploadDocument: async (formData, onUploadProgress) => {
    const response = await api.post('/documents/upload/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress,
    });
    return response.data;
  },

  /**
   * Fetch details of a single document
   * @param {number|string} documentId - ID of the document
   * @returns {Promise<Object>} Document details including extraction_status
   */
  getDocument: async (documentId) => {
    const response = await api.get(`/documents/${documentId}/`);
    return response.data;
  },

  /**
   * Fetch extraction logs for a specific document
   * @param {number|string} documentId - ID of the document
   * @returns {Promise<Array>} List of extraction log records
   */
  getExtractionLogs: async (documentId) => {
    const response = await api.get(`/extraction-logs/`, {
      params: { document_id: documentId }
    });
    return response.data;
  },

  /**
   * Fetch impact stats for document deletion (extracted questions & logs counts)
   * @param {number|string} documentId - ID of the document
   * @returns {Promise<Object>} Statistics object
   */
  getDocumentStats: async (documentId) => {
    const response = await api.get(`/documents/${documentId}/stats/`);
    return response.data;
  },

  /**
   * Update document metadata (title, exam_month, paper_year, document_type, subject)
   * @param {number|string} documentId - ID of the document
   * @param {Object} data - Updated fields
   * @returns {Promise<Object>} Updated document metadata
   */
  updateDocument: async (documentId, data) => {
    const response = await api.patch(`/documents/${documentId}/`, data);
    return response.data;
  },

  /**
   * Delete a document and all associated extracted questions and logs
   * @param {number|string} documentId - ID of the document
   * @returns {Promise<void>}
   */
  deleteDocument: async (documentId) => {
    const response = await api.delete(`/documents/${documentId}/`);
    return response.data;
  },
};

export default documentService;
