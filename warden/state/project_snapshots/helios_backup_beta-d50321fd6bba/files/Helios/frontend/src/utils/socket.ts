import { io, Socket } from 'socket.io-client';

let socket: Socket;

export const getSocket = (): Socket => {
  if (!socket) {
    // Get API URL from environment, ensuring it's a full URL
    const baseUrl = import.meta.env.VITE_API_URL === '/api' 
      ? window.location.origin 
      : (import.meta.env.VITE_API_URL || 'http://localhost:3000');
    
    // Get user data from localStorage
    const savedUser = localStorage.getItem('helios_user');
    const user = savedUser ? JSON.parse(savedUser) : null;

    socket = io(baseUrl, {
      path: '/socket.io',
      autoConnect: true,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      transports: ['websocket', 'polling'],
      withCredentials: true,
      auth: {
        username: user?.username || '',
        team: user?.team || '',
        role: user?.role || '',
        isAuthenticated: user?.isAuthenticated || false
      },
      extraHeaders: {
        'x-helios-username': user?.username || '',
        'x-helios-team': user?.team || '',
        'x-helios-role': user?.role || '',
        'x-helios-authenticated': String(user?.isAuthenticated || false)
      }
    });

    // Socket event listeners
    socket.on('connect', () => {
      console.log('Socket connected to:', baseUrl);
      // Send user info after connection
      if (user) {
        // Update socket auth and headers
        socket.auth = {
          username: user.username,
          team: user.team,
          role: user.role,
          isAuthenticated: true
        };
        socket.io.opts.extraHeaders = {
          'x-helios-username': user.username,
          'x-helios-team': user.team,
          'x-helios-role': user.role,
          'x-helios-authenticated': 'true'
        };
        // Emit user info
        socket.emit('updateUserInfo', {
          username: user.username,
          team: user.team,
          role: user.role,
          isAuthenticated: true
        });
      }
    });

    // Re-authenticate on reconnect
    socket.on('reconnect', () => {
      if (user) {
        // Update socket auth and headers
        socket.auth = {
          username: user.username,
          team: user.team,
          role: user.role,
          isAuthenticated: true
        };
        socket.io.opts.extraHeaders = {
          'x-helios-username': user.username,
          'x-helios-team': user.team,
          'x-helios-role': user.role,
          'x-helios-authenticated': 'true'
        };
        // Emit user info
        socket.emit('updateUserInfo', {
          username: user.username,
          team: user.team,
          role: user.role,
          isAuthenticated: true
        });
        // Wait for authentication before proceeding
        socket.on('userAuthenticated', ({ success }) => {
          if (success) {
            // Re-join team room
            socket.emit('joinTeam', user.team);
          }
        });
      }
    });

    // Re-authenticate on reconnect attempt
    socket.on('reconnect_attempt', () => {
      if (user) {
        socket.auth = {
          username: user.username,
          team: user.team,
          role: user.role,
          isAuthenticated: true
        };
        socket.io.opts.extraHeaders = {
          'x-helios-username': user.username,
          'x-helios-team': user.team,
          'x-helios-role': user.role,
          'x-helios-authenticated': 'true'
        };
      }
    });

    socket.on('disconnect', () => {
      console.log('Socket disconnected');
    });

    socket.on('connect_error', (error) => {
      console.error('Socket connection error:', error);
    });

    socket.on('reconnect_attempt', (attemptNumber) => {
      console.log('Socket reconnection attempt', attemptNumber);
      if (user) {
        // Update socket auth and headers
        socket.auth = {
          username: user.username,
          team: user.team,
          role: user.role,
          isAuthenticated: true
        };
        socket.io.opts.extraHeaders = {
          'x-helios-username': user.username,
          'x-helios-team': user.team,
          'x-helios-role': user.role,
          'x-helios-authenticated': 'true'
        };
      }
    });

    socket.on('reconnect_error', (error) => {
      console.error('Socket reconnection error:', error);
    });

    socket.on('reconnect_failed', () => {
      console.error('Socket reconnection failed');
    });

    // Debug event listeners
    socket.on('chatHistory', (history) => {
      console.log('Received chat history:', history);
    });

    socket.on('chatMessage', (message) => {
      console.log('Received chat message:', message);
    });

    socket.onAny((event, ...args) => {
      console.log('Socket event:', event, args);
    });
  }

  return socket;
};

// Export both the socket instance and the getter
export { socket };
export default getSocket;
