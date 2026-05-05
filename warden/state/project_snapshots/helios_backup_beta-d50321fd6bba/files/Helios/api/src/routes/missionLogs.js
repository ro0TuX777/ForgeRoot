const express = require('express');
const router = express.Router();
const MissionLog = require('../models/MissionLog');
const logger = require('../config/logger');

// Get logs for a specific mission with filtering options
router.get('/missions/:missionId/logs', async (req, res) => {
    try {
        const {
            actionType,
            userId,
            startDate,
            endDate,
            limit,
            offset
        } = req.query;

        const options = {
            actionType,
            userId,
            startDate: startDate ? new Date(startDate) : undefined,
            endDate: endDate ? new Date(endDate) : undefined,
            limit: limit ? parseInt(limit) : undefined,
            offset: offset ? parseInt(offset) : undefined
        };

        const logs = await MissionLog.getMissionLogs(req.params.missionId, options);
        res.json(logs);
    } catch (error) {
        logger.error('Error getting mission logs:', error);
        res.status(500).json({ error: 'Failed to retrieve mission logs' });
    }
});

// Get logs for a specific user with filtering options
router.get('/users/:userId/logs', async (req, res) => {
    try {
        const {
            actionType,
            missionId,
            startDate,
            endDate,
            limit,
            offset
        } = req.query;

        const options = {
            actionType,
            missionId,
            startDate: startDate ? new Date(startDate) : undefined,
            endDate: endDate ? new Date(endDate) : undefined,
            limit: limit ? parseInt(limit) : undefined,
            offset: offset ? parseInt(offset) : undefined
        };

        const logs = await MissionLog.getUserLogs(req.params.userId, options);
        res.json(logs);
    } catch (error) {
        logger.error('Error getting user logs:', error);
        res.status(500).json({ error: 'Failed to retrieve user logs' });
    }
});

// Get action type counts for a mission
router.get('/missions/:missionId/logs/counts', async (req, res) => {
    try {
        const counts = await MissionLog.getActionTypeCounts(req.params.missionId);
        res.json(counts);
    } catch (error) {
        logger.error('Error getting action type counts:', error);
        res.status(500).json({ error: 'Failed to retrieve action type counts' });
    }
});

// Create a new log entry
router.post('/logs', async (req, res) => {
    try {
        const { missionId, userId, actionType, actionData } = req.body;

        // Validate required fields
        if (!missionId || !userId || !actionType) {
            return res.status(400).json({
                error: 'missionId, userId, and actionType are required'
            });
        }

        const log = await MissionLog.create(
            missionId,
            userId,
            actionType,
            actionData || {}
        );

        res.status(201).json(log);
    } catch (error) {
        logger.error('Error creating mission log:', error);
        res.status(500).json({ error: 'Failed to create mission log' });
    }
});

// Get a specific log entry
router.get('/logs/:logId', async (req, res) => {
    try {
        const log = await MissionLog.getById(req.params.logId);
        if (!log) {
            return res.status(404).json({ error: 'Log entry not found' });
        }
        res.json(log);
    } catch (error) {
        logger.error('Error getting log entry:', error);
        res.status(500).json({ error: 'Failed to retrieve log entry' });
    }
});

// Delete old logs (admin only)
router.delete('/logs/cleanup/:days', async (req, res) => {
    try {

        const days = parseInt(req.params.days);
        if (isNaN(days) || days < 1) {
            return res.status(400).json({ error: 'Invalid number of days' });
        }

        const deletedLogs = await MissionLog.deleteOldLogs(days);
        res.json({
            message: `Successfully deleted ${deletedLogs.length} old log entries`,
            deletedCount: deletedLogs.length
        });
    } catch (error) {
        logger.error('Error cleaning up old logs:', error);
        res.status(500).json({ error: 'Failed to clean up old logs' });
    }
});

module.exports = router;
