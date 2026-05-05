const { query } = require('../config/database');
const logger = require('../config/logger');

class MissionLog {
    static async create(missionId, userId, actionType, actionData) {
        try {
            const result = await query(
                `INSERT INTO mission_logs (mission_id, user_id, action_type, action_data)
                 VALUES ($1, $2, $3, $4)
                 RETURNING *`,
                [missionId, userId, actionType, actionData]
            );
            return result.rows[0];
        } catch (error) {
            logger.error('Error creating mission log:', error);
            throw error;
        }
    }

    static async getById(logId) {
        try {
            const result = await query(
                'SELECT * FROM mission_logs WHERE id = $1',
                [logId]
            );
            return result.rows[0];
        } catch (error) {
            logger.error('Error getting mission log:', error);
            throw error;
        }
    }

    static async getMissionLogs(missionId, options = {}) {
        try {
            let query = 'SELECT * FROM mission_logs WHERE mission_id = $1';
            const queryParams = [missionId];
            let paramCount = 1;

            // Add optional filters
            if (options.actionType) {
                paramCount++;
                query += ` AND action_type = $${paramCount}`;
                queryParams.push(options.actionType);
            }

            if (options.userId) {
                paramCount++;
                query += ` AND user_id = $${paramCount}`;
                queryParams.push(options.userId);
            }

            if (options.startDate) {
                paramCount++;
                query += ` AND timestamp >= $${paramCount}`;
                queryParams.push(options.startDate);
            }

            if (options.endDate) {
                paramCount++;
                query += ` AND timestamp <= $${paramCount}`;
                queryParams.push(options.endDate);
            }

            // Add sorting and pagination
            query += ' ORDER BY timestamp DESC';
            
            if (options.limit) {
                paramCount++;
                query += ` LIMIT $${paramCount}`;
                queryParams.push(options.limit);
            }

            if (options.offset) {
                paramCount++;
                query += ` OFFSET $${paramCount}`;
                queryParams.push(options.offset);
            }

            const result = await query(query, queryParams);
            return result.rows;
        } catch (error) {
            logger.error('Error getting mission logs:', error);
            throw error;
        }
    }

    static async getUserLogs(userId, options = {}) {
        try {
            let query = 'SELECT * FROM mission_logs WHERE user_id = $1';
            const queryParams = [userId];
            let paramCount = 1;

            // Add optional filters
            if (options.actionType) {
                paramCount++;
                query += ` AND action_type = $${paramCount}`;
                queryParams.push(options.actionType);
            }

            if (options.missionId) {
                paramCount++;
                query += ` AND mission_id = $${paramCount}`;
                queryParams.push(options.missionId);
            }

            if (options.startDate) {
                paramCount++;
                query += ` AND timestamp >= $${paramCount}`;
                queryParams.push(options.startDate);
            }

            if (options.endDate) {
                paramCount++;
                query += ` AND timestamp <= $${paramCount}`;
                queryParams.push(options.endDate);
            }

            // Add sorting and pagination
            query += ' ORDER BY timestamp DESC';
            
            if (options.limit) {
                paramCount++;
                query += ` LIMIT $${paramCount}`;
                queryParams.push(options.limit);
            }

            if (options.offset) {
                paramCount++;
                query += ` OFFSET $${paramCount}`;
                queryParams.push(options.offset);
            }

            const result = await query(query, queryParams);
            return result.rows;
        } catch (error) {
            logger.error('Error getting user logs:', error);
            throw error;
        }
    }

    static async getActionTypeCounts(missionId) {
        try {
            const result = await query(
                `SELECT action_type, COUNT(*) as count
                 FROM mission_logs 
                 WHERE mission_id = $1
                 GROUP BY action_type
                 ORDER BY count DESC`,
                [missionId]
            );
            return result.rows;
        } catch (error) {
            logger.error('Error getting action type counts:', error);
            throw error;
        }
    }

    static async deleteOldLogs(days) {
        try {
            const result = await query(
                `DELETE FROM mission_logs 
                 WHERE timestamp < NOW() - INTERVAL '$1 days'
                 RETURNING *`,
                [days]
            );
            return result.rows;
        } catch (error) {
            logger.error('Error deleting old logs:', error);
            throw error;
        }
    }
}

module.exports = MissionLog;
