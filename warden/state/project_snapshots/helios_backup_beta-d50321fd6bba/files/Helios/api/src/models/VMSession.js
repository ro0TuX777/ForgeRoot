const { query } = require('../config/database');
const logger = require('../config/logger');

class VMSession {
    static async create(userId, missionId, sessionData) {
        try {
            const result = await query(
                `INSERT INTO vm_sessions (user_id, mission_id, session_data)
                 VALUES ($1, $2, $3)
                 RETURNING *`,
                [userId, missionId, sessionData]
            );
            return result.rows[0];
        } catch (error) {
            logger.error('Error creating VM session:', error);
            throw error;
        }
    }

    static async getById(sessionId) {
        try {
            const result = await query(
                'SELECT * FROM vm_sessions WHERE id = $1',
                [sessionId]
            );
            return result.rows[0];
        } catch (error) {
            logger.error('Error getting VM session:', error);
            throw error;
        }
    }

    static async getByUserAndMission(userId, missionId) {
        try {
            const result = await query(
                'SELECT * FROM vm_sessions WHERE user_id = $1 AND mission_id = $2',
                [userId, missionId]
            );
            return result.rows[0];
        } catch (error) {
            logger.error('Error getting VM session by user and mission:', error);
            throw error;
        }
    }

    static async updateSessionData(sessionId, sessionData) {
        try {
            const result = await query(
                `UPDATE vm_sessions 
                 SET session_data = $2, last_active = CURRENT_TIMESTAMP
                 WHERE id = $1
                 RETURNING *`,
                [sessionId, sessionData]
            );
            return result.rows[0];
        } catch (error) {
            logger.error('Error updating VM session data:', error);
            throw error;
        }
    }

    static async updateLastActive(sessionId) {
        try {
            const result = await query(
                `UPDATE vm_sessions 
                 SET last_active = CURRENT_TIMESTAMP
                 WHERE id = $1
                 RETURNING *`,
                [sessionId]
            );
            return result.rows[0];
        } catch (error) {
            logger.error('Error updating VM session last active:', error);
            throw error;
        }
    }

    static async delete(sessionId) {
        try {
            const result = await query(
                'DELETE FROM vm_sessions WHERE id = $1 RETURNING *',
                [sessionId]
            );
            return result.rows[0];
        } catch (error) {
            logger.error('Error deleting VM session:', error);
            throw error;
        }
    }

    static async getUserSessions(userId) {
        try {
            const result = await query(
                'SELECT * FROM vm_sessions WHERE user_id = $1 ORDER BY last_active DESC',
                [userId]
            );
            return result.rows;
        } catch (error) {
            logger.error('Error getting user VM sessions:', error);
            throw error;
        }
    }

    static async getMissionSessions(missionId) {
        try {
            const result = await query(
                'SELECT * FROM vm_sessions WHERE mission_id = $1 ORDER BY last_active DESC',
                [missionId]
            );
            return result.rows;
        } catch (error) {
            logger.error('Error getting mission VM sessions:', error);
            throw error;
        }
    }
}

module.exports = VMSession;
