import axios from 'axios';

// Create axios instance with default config
const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Add request interceptor to add username header
api.interceptors.request.use(
  (config) => {
    // Skip adding headers for initial login
    if (config.url === '/auth/username' && config.method === 'post') {
      return config;
    }

    const savedUser = localStorage.getItem('helios_user');
    if (savedUser) {
      const user = JSON.parse(savedUser);
      config.headers['x-helios-username'] = user.username;
      config.headers['x-helios-team'] = user.team;
      config.headers['x-helios-role'] = user.role;
      config.headers['x-helios-authenticated'] = String(user.isAuthenticated);
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor to handle errors and save auth headers
api.interceptors.response.use(
  (response) => {
    // Save auth headers from successful login
    if (response.config.url === '/auth/username' && response.config.method === 'post') {
      const headers = response.headers;
      if (headers['x-helios-username']) {
        const user = {
          username: headers['x-helios-username'],
          team: headers['x-helios-team'],
          role: headers['x-helios-role'],
          isAuthenticated: headers['x-helios-authenticated'] === 'true'
        };
        localStorage.setItem('helios_user', JSON.stringify(user));
      }
    }
    return response;
  },
  (error) => {
    if (error.response) {
      // Server responded with error status
      console.error('API Error Response:', error.response.data);
      return Promise.reject(error.response.data);
    } else if (error.request) {
      // Request made but no response
      console.error('API No Response:', error.request);
      return Promise.reject({ error: 'No response from server' });
    } else {
      // Error in request setup
      console.error('API Request Error:', error.message);
      return Promise.reject({ error: error.message });
    }
  }
);

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

interface User {
  id: string;
  username: string;
  role: string;
  status: string;
  team: string;
}

interface Document {
  name: string;
  size: number;
  modified: Date;
  selected?: boolean;
}

// Auth endpoints
export const setUsername = async (username: string, team: string, role: string): Promise<ApiResponse<User>> => {
  try {
    const response = await api.post('/auth/username', { username, team, role });
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('Set Username Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to set username';
    return {
      success: false,
      error: errorMessage
    };
  }
};

// Document operations
export const listDocuments = async (team: string): Promise<ApiResponse<Document[]>> => {
  try {
    const encodedTeam = encodeURIComponent(team);
    const response = await api.get(`/documents/${encodedTeam}`);
    return {
      success: true,
      data: response.data.data
    };
  } catch (error: any) {
    console.error('List Documents Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to list documents';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const getDocument = async (team: string, filename: string): Promise<ApiResponse<string>> => {
  try {
    const encodedTeam = encodeURIComponent(team);
    const encodedFilename = encodeURIComponent(filename);
    const response = await api.get(`/documents/${encodedTeam}/${encodedFilename}`);
    return {
      success: true,
      data: response.data.data
    };
  } catch (error: any) {
    console.error('Get Document Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to get document';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const uploadDocument = async (team: string, file: File): Promise<ApiResponse<void>> => {
  try {
    const formData = new FormData();
    formData.append('file', file);

    // Preserve x-helios-username header while setting content-type to multipart/form-data
    const savedUser = localStorage.getItem('helios_user');
    const headers: Record<string, string> = {
      'Content-Type': 'multipart/form-data'
    };
    if (savedUser) {
      const user = JSON.parse(savedUser);
      headers['x-helios-username'] = user.username;
      headers['x-helios-team'] = user.team;
      headers['x-helios-role'] = user.role;
      headers['x-helios-authenticated'] = String(user.isAuthenticated);
    }

    const encodedTeam = encodeURIComponent(team);
    const response = await api.post(`/documents/${encodedTeam}/upload`, formData, {
      headers
    });
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('Upload Document Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to upload document';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const shareDocuments = async (documents: string[], targetTeams: string[]): Promise<ApiResponse<void>> => {
  try {
    // Encode document names that might contain spaces
    const encodedDocuments = documents.map(doc => encodeURIComponent(doc));
    const response = await api.post('/documents/share', { documents: encodedDocuments, targetTeams });
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('Share Documents Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to share documents';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const createDocument = async (team: string, filename: string, content: string): Promise<ApiResponse<void>> => {
  try {
    const encodedTeam = encodeURIComponent(team);
    const encodedFilename = encodeURIComponent(filename);
    const response = await api.post(`/documents/${encodedTeam}/${encodedFilename}`, { content });
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('Create Document Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to create document';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const updateDocument = async (team: string, filename: string, content: string): Promise<ApiResponse<void>> => {
  try {
    const encodedTeam = encodeURIComponent(team);
    const encodedFilename = encodeURIComponent(filename);
    const response = await api.put(`/documents/${encodedTeam}/${encodedFilename}`, { content });
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('Update Document Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to update document';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const deleteDocument = async (team: string, filename: string): Promise<ApiResponse<void>> => {
  try {
    const encodedTeam = encodeURIComponent(team);
    const encodedFilename = encodeURIComponent(filename);
    const response = await api.delete(`/documents/${encodedTeam}/${encodedFilename}`);
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('Delete Document Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to delete document';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const getChatHistory = async (): Promise<ApiResponse<any>> => {
  try {
    const response = await api.get('/chat/history');
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('Get Chat History Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to get chat history';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export default api;
