import axios from 'axios';

// Create base Axios instance pointing to the backend API via proxy
const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000, // 15 seconds timeout
});

export default api;
