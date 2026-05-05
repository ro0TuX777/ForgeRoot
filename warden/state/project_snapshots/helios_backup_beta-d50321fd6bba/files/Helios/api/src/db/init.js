const { pool } = require('../config/database');
const logger = require('../config/logger');
const fs = require('fs');
const path = require('path');

async function initializeDatabase() {
  let client;
  try {
    logger.info('Starting database initialization...');
    
    // Read schema file
    const schemaPath = path.join(__dirname, 'schema.sql');
    logger.info(`Reading schema from ${schemaPath}`);
    const schema = fs.readFileSync(schemaPath, 'utf8');
    
    // Get client from pool
    logger.info('Acquiring database client...');
    client = await pool.connect();
    
    // Begin transaction
    logger.info('Beginning transaction...');
    await client.query('BEGIN');

    // Execute schema
    logger.info('Executing schema...');
    await client.query(schema);

    // Commit transaction
    logger.info('Committing transaction...');
    await client.query('COMMIT');
    
    logger.info('Database initialized successfully');
    return true;
  } catch (err) {
    logger.error('Error initializing database:', err);
    if (client) {
      try {
        logger.info('Rolling back transaction...');
        await client.query('ROLLBACK');
      } catch (rollbackErr) {
        logger.error('Error rolling back transaction:', rollbackErr);
      }
    }
    // Don't throw error, just return false to indicate failure
    return false;
  } finally {
    if (client) {
      logger.info('Releasing database client...');
      client.release();
    }
  }
}

module.exports = initializeDatabase;
