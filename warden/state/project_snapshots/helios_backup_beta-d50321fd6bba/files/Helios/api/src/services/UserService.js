const db = require('../config/database');
const logger = require('../config/logger');

class UserService {
  /**
   * Create or update a user
   */
  async setUsername(username, team, role) {
    try {
      console.log('UserService.setUsername called with:', { username, team, role });
      
      // Validate username
      if (!username || typeof username !== 'string' || username.trim().length === 0) {
        throw new Error('Invalid username');
      }

      // Validate team
      if (!team || !['red', 'blue', 'white', 'observer'].includes(team)) {
        throw new Error('Invalid team');
      }

      // Validate role
      if (!role) {
        throw new Error('Role is required');
      }

      const trimmedUsername = username.trim();

      // Begin transaction
      const client = await db.getClient();
      try {
        await client.query('BEGIN');
        console.log('Transaction started');

        // Check if username exists
        const existingUser = await client.query(
          'SELECT id FROM users WHERE username = $1',
          [trimmedUsername]
        );

        let userId;

        console.log('Existing user check result:', existingUser.rows);
        
        if (existingUser.rows.length > 0) {
          // Update existing user's status, team, role, and authentication
          userId = existingUser.rows[0].id;
          await client.query(
            `UPDATE users 
             SET status = 'online',
                 team = $2,
                 role = $3,
                 last_login = CURRENT_TIMESTAMP,
                 is_authenticated = true
             WHERE id = $1`,
            [userId, team, role]
          );
          logger.debug('Updated existing user:', { userId, team, role });
        } else {
          // Create new user with explicit NULL password_hash, team field, and is_authenticated
          const result = await client.query(
            `INSERT INTO users (username, password_hash, role, status, team, created_at, last_login, is_authenticated)
             VALUES ($1, NULL, $2, 'online', $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, true)
             RETURNING id`,
            [trimmedUsername, role, team]
          );
          userId = result.rows[0].id;
          logger.debug('Created new user:', { userId, team, role });
        }

        // Get user details
        const userResult = await client.query(
          `SELECT id, username, role, status::varchar(20) as status, team, is_authenticated
           FROM users 
           WHERE id = $1`,
          [userId]
        );

        console.log('Final user result:', userResult.rows[0]);
        await client.query('COMMIT');
        console.log('Transaction committed');

        const user = {
          ...userResult.rows[0],
          isAuthenticated: true
        };
        logger.info(`User authenticated: ${JSON.stringify(user)}`);

        console.log('Returning successful response:', user);
        return {
          success: true,
          data: user
        };
      } catch (error) {
        await client.query('ROLLBACK');
        throw error;
      } finally {
        client.release();
      }
    } catch (error) {
      logger.error('Error in UserService.setUsername:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Update user status
   */
  async updateStatus(userId, status) {
    try {
      if (!['online', 'offline', 'away', 'SIGNED OUT'].includes(status)) {
        throw new Error('Invalid status');
      }

      const result = await db.query(
        `UPDATE users 
         SET status = $1::varchar(20), 
             last_login = CASE 
                 WHEN $1::varchar(20) = 'online' THEN CURRENT_TIMESTAMP 
                 ELSE last_login 
             END
         WHERE id = $2
         RETURNING id, username, role, status::varchar(20) as status, is_authenticated`,
        [status, userId]
      );

      if (result.rows.length === 0) {
        throw new Error('User not found');
      }

      const user = {
        ...result.rows[0],
        isAuthenticated: true
      };
      return {
        success: true,
        data: user
      };
    } catch (error) {
      logger.error('Error in UserService.updateStatus:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Validate user by username, team, and role
   */
  async validateUser(username, team, role) {
    try {
      const result = await db.query(
        `SELECT id, username, role, status::varchar(20) as status, team, is_authenticated
         FROM users 
         WHERE username = $1 AND team = $2 AND role = $3`,
        [username, team, role]
      );

      if (result.rows.length === 0) {
        return {
          success: false,
          error: 'User not found or unauthorized'
        };
      }

      return {
        success: true,
        data: result.rows[0]
      };
    } catch (error) {
      logger.error('Error in UserService.validateUser:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Get user status
   */
  async getStatus(userId) {
    try {
      const result = await db.query(
        `SELECT status::varchar(20) as status, is_authenticated
         FROM users 
         WHERE id = $1`,
        [userId]
      );

      if (result.rows.length === 0) {
        throw new Error('User not found');
      }

      return {
        success: true,
        data: result.rows[0]
      };
    } catch (error) {
      logger.error('Error in UserService.getStatus:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }
}

module.exports = new UserService();
