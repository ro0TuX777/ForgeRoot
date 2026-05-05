const Redis = require('redis');
const logger = require('./logger');

// Create Redis client with improved configuration
const createClient = () => {
  console.log('Creating Redis client...');
  const client = Redis.createClient({
    url: process.env.REDIS_URL || 'redis://redis:6379',
    legacyMode: false,
    socket: {
      reconnectStrategy: (retries) => {
        const maxRetries = 20; // Increased max retries
        if (retries > maxRetries) {
          logger.error('Redis max retries reached, giving up');
          return new Error('Redis max retries reached');
        }
        // Exponential backoff with max delay of 10 seconds
        const delay = Math.min(Math.pow(2, retries) * 100, 10000);
        logger.info(`Retrying Redis connection in ${delay}ms... (attempt ${retries}/${maxRetries})`);
        return delay;
      },
      connectTimeout: 10000, // 10 seconds
      keepAlive: 30000 // 30 seconds
    },
    // Disable auto-reconnect to handle it manually
    autoReconnect: false
  });

  // Enhanced event handlers with better logging
  client.on('connect', () => {
    logger.info('Redis client connected');
  });

  client.on('ready', () => {
    logger.info('Redis client ready and accepting commands');
  });

  client.on('error', (err) => {
    logger.error('Redis client error:', {
      error: err.message,
      code: err.code,
      stack: err.stack
    });
  });

  client.on('reconnecting', (params) => {
    logger.info('Redis client reconnecting:', {
      attempt: params?.attempt,
      delay: params?.delay
    });
  });

  client.on('end', () => {
    logger.info('Redis client connection closed');
  });

  return client;
};

// Test Redis connection with retries
const testConnection = async (client, retries = 5, delay = 2000) => {
  let lastError;
  
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      if (!client.isOpen) {
        await client.connect();
      }
      await client.ping();
      logger.info('Redis connection test successful');
      return true;
    } catch (err) {
      lastError = err;
      logger.warn(`Redis connection test attempt ${attempt}/${retries} failed:`, {
        error: err.message,
        code: err.code
      });
      
      if (attempt < retries) {
        logger.info(`Retrying Redis connection test in ${delay}ms...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  logger.error('Redis connection test failed after all retries:', {
    error: lastError.message,
    code: lastError.code,
    stack: lastError.stack
  });
  return false;
};

// Create client instance
console.log('Initializing Redis client...');
const client = createClient();

// Wrapper for Redis commands with retry logic
const executeWithRetry = async (command, ...args) => {
  const maxRetries = 3;
  let lastError;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      if (!client.isOpen) {
        await client.connect();
      }
      return await command.apply(client, args);
    } catch (err) {
      lastError = err;
      logger.warn(`Redis command failed, attempt ${attempt}/${maxRetries}:`, {
        error: err.message,
        command: command.name,
        args
      });

      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
      }
    }
  }

  throw lastError;
};

// Export enhanced client interface
module.exports = {
  client,
  testConnection: () => testConnection(client),
  get: async (key) => executeWithRetry(client.get, key),
  set: async (key, value, options) => executeWithRetry(client.set, key, value, options),
  del: async (key) => executeWithRetry(client.del, key),
  disconnect: async () => {
    logger.info('Closing Redis connection');
    try {
      await client.quit();
      logger.info('Redis connection closed successfully');
    } catch (err) {
      logger.error('Error closing Redis connection:', {
        error: err.message,
        code: err.code,
        stack: err.stack
      });
      throw err;
    }
  }
};
