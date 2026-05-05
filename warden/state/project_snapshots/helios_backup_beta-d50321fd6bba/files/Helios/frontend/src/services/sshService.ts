import api from '@/utils/api';
import { SSHCredentials, SSHConnection } from '@/types/ssh';

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export const connectSSH = async (credentials: SSHCredentials): Promise<ApiResponse<SSHConnection>> => {
  try {
    const response = await api.post('/terminal/connect', credentials);
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('SSH Connect Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to connect SSH';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const disconnectSSH = async (connectionId: string): Promise<ApiResponse<void>> => {
  try {
    const response = await api.post(`/terminal/disconnect/${connectionId}`);
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('SSH Disconnect Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to disconnect SSH';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const getSSHStatus = async (connectionId: string): Promise<ApiResponse<SSHConnection>> => {
  try {
    const response = await api.get(`/terminal/status/${connectionId}`);
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('SSH Status Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to get SSH status';
    return {
      success: false,
      error: errorMessage
    };
  }
};

export const listConnections = async (): Promise<ApiResponse<SSHConnection[]>> => {
  try {
    const response = await api.get('/terminal/connections');
    return {
      success: true,
      data: response.data
    };
  } catch (error: any) {
    console.error('List SSH Connections Error:', error);
    const errorMessage = error.response?.data?.error || error.message || 'Failed to list SSH connections';
    return {
      success: false,
      error: errorMessage
    };
  }
};
