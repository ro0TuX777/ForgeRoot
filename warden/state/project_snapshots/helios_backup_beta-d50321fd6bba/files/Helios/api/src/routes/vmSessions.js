const express = require('express');
const router = express.Router();
const VMSession = require('../models/VMSession');
const MissionLog = require('../models/MissionLog');
const logger = require('../config/logger');

// Get all VM sessions for a user
router.get('/users/:userId/vm-sessions', async (req, res) => {
    try {
        const sessions = await VMSession.getUserSessions(req.params.userId);
        res.json(sessions);
    } catch (error) {
        logger.error('Error getting user VM sessions:', error);
        res.status(500).json({ error: 'Failed to retrieve VM sessions' });
    }
});

// Get VM sessions for a mission
router.get('/missions/:missionId/vm-sessions', async (req, res) => {
    try {
        const sessions = await VMSession.getMissionSessions(req.params.missionId);
        res.json(sessions);
    } catch (error) {
        logger.error('Error getting mission VM sessions:', error);
        res.status(500).json({ error: 'Failed to retrieve VM sessions' });
    }
});

// Create a new VM session
router.post('/vm-sessions', async (req, res) => {
    try {
        const { userId, missionId, sessionData } = req.body;

        // Validate required fields
        if (!userId || !missionId) {
            return res.status(400).json({ error: 'userId and missionId are required' });
        }

        const session = await VMSession.create(userId, missionId, sessionData || {});
        
        // Log the session creation
        await MissionLog.create(missionId, userId, 'VM_SESSION_START', {
            sessionId: session.id,
            timestamp: new Date().toISOString()
        });

        res.status(201).json(session);
    } catch (error) {
        logger.error('Error creating VM session:', error);
        res.status(500).json({ error: 'Failed to create VM session' });
    }
});

// Get a specific VM session
router.get('/vm-sessions/:sessionId', async (req, res) => {
    try {
        const session = await VMSession.getById(req.params.sessionId);
        if (!session) {
            return res.status(404).json({ error: 'VM session not found' });
        }
        res.json(session);
    } catch (error) {
        logger.error('Error getting VM session:', error);
        res.status(500).json({ error: 'Failed to retrieve VM session' });
    }
});

// Update VM session data
router.patch('/vm-sessions/:sessionId', async (req, res) => {
    try {
        const { sessionData } = req.body;
        const session = await VMSession.updateSessionData(req.params.sessionId, sessionData);
        
        if (!session) {
            return res.status(404).json({ error: 'VM session not found' });
        }

        // Log the session update
        const { userId } = req.body;
        if (!userId) {
            return res.status(400).json({ error: 'userId is required' });
        }
        await MissionLog.create(session.mission_id, userId, 'VM_SESSION_UPDATE', {
            sessionId: session.id,
            timestamp: new Date().toISOString()
        });

        res.json(session);
    } catch (error) {
        logger.error('Error updating VM session:', error);
        res.status(500).json({ error: 'Failed to update VM session' });
    }
});

// Update VM session last active timestamp
router.post('/vm-sessions/:sessionId/heartbeat', async (req, res) => {
    try {
        const session = await VMSession.updateLastActive(req.params.sessionId);
        if (!session) {
            return res.status(404).json({ error: 'VM session not found' });
        }
        res.json(session);
    } catch (error) {
        logger.error('Error updating VM session heartbeat:', error);
        res.status(500).json({ error: 'Failed to update VM session heartbeat' });
    }
});

// Delete a VM session
router.delete('/vm-sessions/:sessionId', async (req, res) => {
    try {
        const session = await VMSession.delete(req.params.sessionId);
        if (!session) {
            return res.status(404).json({ error: 'VM session not found' });
        }

        // Log the session deletion
        const { userId } = req.body;
        if (!userId) {
            return res.status(400).json({ error: 'userId is required' });
        }
        await MissionLog.create(session.mission_id, userId, 'VM_SESSION_END', {
            sessionId: session.id,
            timestamp: new Date().toISOString()
        });

        res.json({ message: 'VM session deleted successfully' });
    } catch (error) {
        logger.error('Error deleting VM session:', error);
        res.status(500).json({ error: 'Failed to delete VM session' });
    }
});

module.exports = router;
