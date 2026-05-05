const express = require('express');
const router = express.Router();
const sshService = require('../services/SSHService');
const authMiddleware = require('../middleware/auth');
const { logError } = require('../config/logger');

// Middleware to check if user has SSH access
const checkSSHAccess = (req, res, next) => {
    if (req.user.team === 'observer') {
        return res.status(403).json({
            error: 'Forbidden',
            message: 'SSH access not available for observers'
        });
    }
    next();
};

// Create new SSH session
router.post('/sessions', authMiddleware, checkSSHAccess, async (req, res) => {
    try {
        const { host, port, username, password } = req.body;

        if (!host || !username || !password) {
            return res.status(400).json({
                error: 'Bad Request',
                message: 'Missing required connection parameters'
            });
        }

        const sessionId = await sshService.createSession(req.user.id, {
            host,
            port: port || 22,
            username,
            password
        });

        res.json({ sessionId });
    } catch (error) {
        logError('Failed to create SSH session:', { error });
        res.status(500).json({
            error: 'Internal Server Error',
            message: error.message || 'Failed to create SSH session'
        });
    }
});

// WebSocket handling will be set up in the main app file
const setupTerminalWebSocket = (io) => {
    io.of('/api/terminal').use(async (socket, next) => {
        // Extract session ID from URL
        const sessionId = socket.handshake.query.sessionId;
        if (!sessionId) {
            return next(new Error('Session ID required'));
        }

        const session = sshService.getSession(sessionId);
        if (!session) {
            return next(new Error('Invalid session'));
        }

        socket.sessionId = sessionId;
        next();
    });

    io.of('/api/terminal').on('connection', (socket) => {
        const sessionId = socket.sessionId;
        const session = sshService.getSession(sessionId);

        if (!session) {
            socket.disconnect();
            return;
        }

        // Handle incoming data from client
        socket.on('data', (data) => {
            try {
                sshService.handleData(sessionId, data);
            } catch (error) {
                logError('Error handling terminal data:', { error, sessionId });
            }
        });

        // Handle terminal resize
        socket.on('resize', ({ rows, cols }) => {
            try {
                sshService.handleResize(sessionId, rows, cols);
            } catch (error) {
                logError('Error handling terminal resize:', { error, sessionId });
            }
        });

        // Forward SSH stream data to client
        session.stream.on('data', (data) => {
            socket.emit('data', data.toString('utf-8'));
        });

        session.stream.on('close', () => {
            socket.disconnect();
            sshService.closeSession(sessionId);
        });

        socket.on('disconnect', () => {
            sshService.closeSession(sessionId);
        });
    });
};

module.exports = {
    router,
    setupTerminalWebSocket
};
