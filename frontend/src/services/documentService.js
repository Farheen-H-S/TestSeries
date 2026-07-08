import api from './api';

/**
 * Service to handle document/paper operations with Django backend
 */
const documentService = {
  /**
   * Fetch all documents from the backend
   * @returns {Promise<Array>} List of document items
   */
  getDocuments: async () => {
    const response = await api.get('/documents/');
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
};

export default documentService;
