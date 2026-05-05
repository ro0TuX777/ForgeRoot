const { Pool } = require('pg');
const logger = require('./logger');

// Log environment variables
console.log('Environment variables:', {
  DATABASE_URL: process.env.DATABASE_URL,
  POSTGRES_USER: process.env.POSTGRES_USER,
  POSTGRES_PASSWORD: process.env.POSTGRES_PASSWORD,
  POSTGRES_DB: process.env.POSTGRES_DB,
  NODE_ENV: process.env.NODE_ENV,
  PWD: process.env.PWD,
  __dirname: __dirname
});

console.log('Configuring database connection...');

// Create a connection pool using environment variables
const config = {
  user: process.env.POSTGRES_USER,
  host: process.env.NODE_ENV === 'production' ? 'db' : 'localhost',
  database: process.env.POSTGRES_DB,
  port: 5432,
  password: process.env.POSTGRES_PASSWORD,
  max: 20, // Maximum number of clients in the pool
  idleTimeoutMillis: 30000, // Close idle clients after 30 seconds
  connectionTimeoutMillis: 10000, // Increased timeout to 10 seconds for container environment
  maxUses: 10000 // Increased to reduce connection churn
};

console.log('Database config:', config);

const pool = new Pool(config);

console.log('Database pool created');

// Add event listeners with improved logging
pool.on('connect', () => {
  logger.info('New client connected to database');
});

pool.on('error', (err, client) => {
  logger.error('Unexpected database error:', {
    error: err.message,
    code: err.code,
    stack: err.stack
  });
});

pool.on('remove', () => {
  logger.debug('Client removed from pool');
});

pool.on('acquire', () => {
  logger.debug('Client acquired from pool');
});

// Test database connection with retries
const testConnection = async (retries = 5, delay = 2000) => {
  let lastError;
  
  for (let attempt = 1; attempt <= retries; attempt++) {
    let client;
    try {
      client = await pool.connect();
      await client.query('SELECT NOW()');
      logger.info('Database connection successful');
      return true;
    } catch (err) {
      lastError = err;
      logger.warn(`Database connection attempt ${attempt}/${retries} failed:`, {
        error: err.message,
        code: err.code
      });
      
      if (attempt < retries) {
        logger.info(`Retrying in ${delay}ms...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    } finally {
      if (client) {
        client.release();
      }
    }
  }

  logger.error('Database connection failed after all retries:', {
    error: lastError.message,
    code: lastError.code,
    stack: lastError.stack
  });
  return false;
};

// Query wrapper with retries
const queryWithRetry = async (text, params, retries = 3) => {
  let lastError;
  
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const result = await pool.query(text, params);
      if (attempt > 1) {
        logger.info(`Query succeeded after ${attempt} attempts`);
      }
      return result;
    } catch (err) {
      lastError = err;
      if (attempt < retries && (err.code === '40P01' || err.code === '40001' || err.code === '40P02')) {
        // Retry on serialization failures and deadlocks
        logger.warn(`Query attempt ${attempt}/${retries} failed:`, {
          error: err.message,
          code: err.code
        });
        await new Promise(resolve => setTimeout(resolve, 100 * attempt));
        continue;
      }
      throw err;
    }
  }
  
  throw lastError;
};

// Export pool and functions
module.exports = {
  pool,
  testConnection,
  query: async (text, params) => {
    logger.debug('Executing query:', { text, params });
    try {
      const result = await queryWithRetry(text, params);
      logger.debug('Query result:', { 
        command: result.command,
        rowCount: result.rowCount
      });
      return result;
    } catch (error) {
      logger.error('Query error:', { 
        error: error.message,
        detail: error.detail,
        code: error.code,
        query: text
      });
      throw error;
    }
  },
  getClient: async () => {
    let attempts = 0;
    const maxAttempts = 3;
    
    while (attempts < maxAttempts) {
      try {
        const client = await pool.connect();
        const originalRelease = client.release;
        
        // Wrap release to keep track of client state
        client.release = () => {
          client.lastQuery = null;
          return originalRelease.apply(client);
        };
        
        logger.debug('Client acquired from pool');
        return client;
      } catch (error) {
        attempts++;
        if (attempts === maxAttempts) {
          logger.error('Failed to acquire client after all retries:', {
            error: error.message,
            code: error.code
          });
          throw error;
        }
        logger.warn(`Failed to acquire client, attempt ${attempts}/${maxAttempts}:`, {
          error: error.message,
          code: error.code
        });
        await new Promise(resolve => setTimeout(resolve, 1000 * attempts));
      }
    }
  },
  end: async () => {
    logger.info('Closing database pool');
    try {
      await pool.end();
      logger.info('Database pool closed successfully');
    } catch (error) {
      logger.error('Error closing database pool:', {
        error: error.message,
        code: error.code
      });
      throw error;
    }
  }
};
