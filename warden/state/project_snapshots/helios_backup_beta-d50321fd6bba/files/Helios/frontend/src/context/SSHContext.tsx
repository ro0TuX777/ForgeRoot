import React, { createContext, useContext, useState, useCallback } from 'react';
import { SSHContextType, SSHConnection, SSHCredentials } from '@/types/ssh';
import * as sshService from '@/services/sshService';

export const SSHContext = createContext<SSHContextType | null>(null);

export const useSSH = () => {
  const context = useContext(SSHContext);
  if (!context) {
    throw new Error('useSSH must be used within an SSHProvider');
  }
  return context;
};

export default SSHContext;

export const SSHProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [connections, setConnections] = useState<SSHConnection[]>([]);
  const [currentConnection, setCurrentConnection] = useState<SSHConnection | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(async (credentials: SSHCredentials) => {
    setIsConnecting(true);
    setError(null);
    try {
      const response = await sshService.connectSSH(credentials);
      if (response.success && response.data) {
        const newConnection = response.data;
        setCurrentConnection(newConnection);
        setConnections(prev => [...prev, newConnection]);
      } else {
        setError(response.error || 'Failed to connect');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
    } finally {
      setIsConnecting(false);
    }
  }, []);

  const disconnect = useCallback(async () => {
    if (!currentConnection) return;
    
    try {
      const response = await sshService.disconnectSSH(currentConnection.id);
      if (response.success) {
        setConnections(connections => {
          return connections.filter(conn => {
            return conn.id !== currentConnection.id;
          }) as SSHConnection[];
        });
        setCurrentConnection(null);
      } else {
        setError(response.error || 'Failed to disconnect');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
    }
  }, [currentConnection]);

  // Load existing connections on mount
  React.useEffect(() => {
    const loadConnections = async () => {
      try {
        const response = await sshService.listConnections();
        if (response.success && response.data) {
          setConnections(response.data);
          // Set the first active connection as current if exists
          const activeConnection = response.data.find(conn => conn.status === 'connected');
          if (activeConnection) {
            setCurrentConnection(activeConnection);
          }
        }
      } catch (err) {
        console.error('Failed to load SSH connections:', err);
      }
    };
    loadConnections();
  }, []);

  const value: SSHContextType = {
    connections,
    currentConnection,
    isConnecting,
    connect,
    disconnect,
    error
  };

  return (
    <SSHContext.Provider value={value}>
      {children}
    </SSHContext.Provider>
  );
};
