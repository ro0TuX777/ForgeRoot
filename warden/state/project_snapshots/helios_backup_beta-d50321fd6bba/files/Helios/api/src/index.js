const express = require('express');
const cors = require('cors');
const logger = require('./config/logger');
const db = require('./config/database');
const redis = require('./config/redis');
const ChatService = require('./services/ChatService');
const http = require('http');
const socketIo = require('socket.io');
const errorHandler = require('./middleware/errorHandler');
const { initialize: initDocumentService, service: DocumentService } = require('./services/DocumentService');

const setupRoutes = async (app, io, chatService) => {
  try {
    console.log('Loading routes...');
    // Import routes
    const authRoutes = require('./routes/auth');
    const chatRoutes = require('./routes/chat');
    const systemRoutes = require('./routes/system');
    const missionLogRoutes = require('./routes/missionLogs');
    const vmSessionRoutes = require('./routes/vmSessions');
    const documentRoutes = require('./routes/documents');
    const { router: terminalRoutes, setupTerminalWebSocket } = require('./routes/terminal');

    console.log('Setting up routes...');
    // Routes
    app.use('/api/auth', authRoutes);
    app.use('/api/chat', chatRoutes(chatService));
    app.use('/api/system', systemRoutes);
    app.use('/api/mission-logs', missionLogRoutes);
    app.use('/api/vm-sessions', vmSessionRoutes);
    app.use('/api/documents', documentRoutes(io));
    app.use('/api/terminal', terminalRoutes);

    console.log('Setting up terminal WebSocket...');
    // Initialize terminal WebSocket handling
    setupTerminalWebSocket(io);

    console.log('Routes setup completed successfully');
  } catch (error) {
    logger.error('Error setting up routes:', {
      error: error.message,
      stack: error.stack,
      name: error.name
    });
    throw error;
  }
};

// Initialize database
const initializeDatabase = require('./db/init');

// Initialize server function with retries
const initializeServer = async (retryCount = 0) => {
  const MAX_RETRIES = 5;
  const RETRY_DELAY = 5000; // 5 seconds

  try {
    console.log('Starting server initialization...');
    
    // Test database connection with retries
    logger.info('Testing database connection...');
    const connected = await db.testConnection();
    if (!connected) {
      throw new Error('Database connection test failed');
    }
    logger.info('Database connection successful');
    
    // Test Redis connection
    logger.info('Testing Redis connection...');
    const redisConnected = await redis.testConnection();
    if (!redisConnected) {
      throw new Error('Redis connection test failed');
    }
    logger.info('Redis connection successful');
    
    // Initialize database
    logger.info('Running database initialization...');
    const initialized = await initializeDatabase();
    if (!initialized) {
      throw new Error('Database initialization failed');
    }
    logger.info('Database initialized successfully');

    // Create Express app and server
    console.log('Creating Express app...');
    const app = express();
    const server = http.createServer(app);

    // Configure Socket.IO
    console.log('Configuring Socket.IO...');
    const io = socketIo(server, {
      cors: {
        origin: "*",
        methods: ["GET", "POST"],
        allowedHeaders: ["Content-Type", "Authorization", "x-helios-username", "x-helios-team", "x-helios-role"]
      }
    });

    // Initialize chat service with socket.io instance
    console.log('Initializing chat service...');
    const chatService = new ChatService(io);
    await chatService.initialize();
    logger.info('Chat service initialized successfully');

    // Initialize DocumentService
    logger.info('Initializing DocumentService...');
    await initDocumentService();
    logger.info('DocumentService initialized successfully');

    // Setup middleware
    console.log('Setting up middleware...');
    app.use(cors({
      origin: '*',
      methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
      allowedHeaders: ['Content-Type', 'Authorization', 'x-helios-username', 'x-helios-team', 'x-helios-role']
    }));

    // Setup file upload middleware
    console.log('Setting up file upload middleware...');
    app.use((req, res, next) => {
      if (req.path === '/api/documents/upload' && req.method === 'POST') {
        next();
      } else {
        express.json()(req, res, next);
      }
    });

    // Setup health check endpoint
    console.log('Setting up health check endpoint...');
    app.get('/health', (req, res) => {
      res.json({ status: 'ok' });
    });

    // Setup routes with error handling
    await setupRoutes(app, io, chatService);

    // Setup error handler
    console.log('Setting up error handler...');
    app.use(errorHandler);

    const PORT = process.env.PORT || 3001;

    // Start server with error handling
    await new Promise((resolve, reject) => {
      try {
        console.log(`Starting server on port ${PORT}...`);
        const serverInstance = server.listen(PORT, () => {
          logger.info(`Server running on port ${PORT}`);
          console.log(`Server running on port ${PORT}`);
          resolve(serverInstance);
        });

        serverInstance.on('error', (error) => {
          logger.error('Server error:', {
            error: error.message,
            code: error.code,
            stack: error.stack
          });
          reject(error);
        });
      } catch (error) {
        reject(error);
      }
    });

    return server;

  } catch (err) {
    console.error('Server initialization failed:', err);
    logger.error('Server initialization failed:', {
      error: err.message,
      stack: err.stack,
      name: err.name,
      retryCount
    });

    if (retryCount < MAX_RETRIES) {
      logger.info(`Retrying initialization in ${RETRY_DELAY}ms... (Attempt ${retryCount + 1}/${MAX_RETRIES})`);
      await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
      return initializeServer(retryCount + 1);
    } else {
      logger.error(`Failed to initialize server after ${MAX_RETRIES} attempts`);
      throw err;
    }
  }
};

// Start the server
let server;
initializeServer()
  .then(serverInstance => {
    server = serverInstance;
  })
  .catch(err => {
    logger.error('Fatal error during server initialization:', {
      error: err.message,
      stack: err.stack,
      name: err.name
    });
    // Don't exit immediately to allow logs to be written
    setTimeout(() => {
      logger.info('Shutting down after fatal error');
      process.exit(1);
    }, 1000);
  });

// Handle process termination
process.on('SIGTERM', async () => {
  console.log('SIGTERM received. Shutting down gracefully...');
  logger.info('SIGTERM received. Shutting down gracefully...');
  try {
    if (server) {
      await new Promise((resolve) => {
        server.close(() => {
          logger.info('Server closed');
          resolve();
        });
      });
    }
    await db.end();
    await redis.disconnect();
    logger.info('All connections closed');
    process.exit(0);
  } catch (error) {
    logger.error('Error during shutdown:', error);
    process.exit(1);
  }
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  console.error('Uncaught Exception:', error);
  logger.error('Uncaught Exception:', {
    error: error.message,
    stack: error.stack,
    name: error.name
  });
  // Log but don't exit - let the error propagate naturally
});

// Handle unhandled promise rejections
process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
  logger.error('Unhandled Rejection at:', {
    reason: reason instanceof Error ? reason.stack : reason,
    promise
  });
  // Log but don't exit - let the error propagate naturally
});
