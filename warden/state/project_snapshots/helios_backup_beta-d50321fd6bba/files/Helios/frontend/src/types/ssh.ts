export interface SSHCredentials {
  host: string;
  port: number;
  username: string;
  password?: string;
  privateKey?: string;
}

export interface SSHConnection {
  id: string;
  status: 'connected' | 'disconnected' | 'error';
  credentials: SSHCredentials;
  error?: string;
}

export interface SSHContextType {
  connections: SSHConnection[];
  currentConnection: SSHConnection | null;
  isConnecting: boolean;
  connect: (credentials: SSHCredentials) => Promise<void>;
  disconnect: () => Promise<void>;
  error: string | null;
}
