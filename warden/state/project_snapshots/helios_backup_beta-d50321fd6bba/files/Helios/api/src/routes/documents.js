const express = require('express');
const logger = require('../config/logger');
const { service: DocumentService } = require('../services/DocumentService');
const UserService = require('../services/UserService');
const authMiddleware = require('../middleware/auth');
const { query } = require('../config/database');

// Export a function that takes io as a parameter
module.exports = function(io) {
  const router = express.Router();

  // Apply auth middleware to all routes
  router.use(authMiddleware);

  // List documents for a team
  router.get('/:team', async (req, res) => {
    try {
      const { team } = req.params;
      const documents = await DocumentService.listDocuments(req.user, team);
      res.json({ success: true, data: documents });
    } catch (error) {
      logger.error('Error listing documents:', error);
      res.status(error.message === 'Access denied' ? 403 : 500).json({
        success: false,
        error: error.message
      });
    }
  });

  // Get a specific document
  router.get('/:team/:filename', async (req, res) => {
    try {
      const { team, filename } = req.params;
      const content = await DocumentService.getDocument(req.user, team, filename);
      res.json({ success: true, data: content });
    } catch (error) {
      logger.error('Error getting document:', error);
      res.status(error.message === 'Access denied' ? 403 : 500).json({
        success: false,
        error: error.message
      });
    }
  });

  // Upload a document
  router.post('/:team/upload', async (req, res) => {
    try {
      const { team } = req.params;
      // Handle file upload
      await DocumentService.handleUpload(req, res);

      if (!req.file) {
        throw new Error('No file uploaded');
      }

      res.json({ success: true });
    } catch (error) {
      logger.error('Error uploading document:', error);
      res.status(error.message.includes('Only White Cell') ? 403 : 500).json({
        success: false,
        error: error.message
      });
    }
  });

  // Share documents with teams
  router.post('/share', async (req, res) => {
    try {
      const { documents, targetTeams } = req.body;
      await DocumentService.shareDocuments(req.user, documents, targetTeams);
      
      // Emit document update events to each target team
      targetTeams.forEach(team => {
        io.to(`team_${team}`).emit('documentsUpdated', {
          team,
          documents
        });
      });
      
      res.json({ success: true });
    } catch (error) {
      logger.error('Error sharing documents:', error);
      res.status(error.message.includes('Only White Cell') ? 403 : 500).json({
        success: false,
        error: error.message
      });
    }
  });

  // Delete a document
  router.delete('/:team/:filename', async (req, res) => {
    try {
      const { team, filename } = req.params;
      await DocumentService.deleteDocument(req.user, team, filename);
      res.json({ success: true });
    } catch (error) {
      logger.error('Error deleting document:', error);
      res.status(error.message.includes('Only White Cell') ? 403 : 500).json({
        success: false,
        error: error.message
      });
    }
  });

  // Socket event handlers
  io.on('connection', (socket) => {
    // Store user info
    let userInfo = null;

    socket.on('updateUserInfo', async (info) => {
      try {
        // Validate team and role combinations
        if (info.team === 'white' && info.role !== 'Operational Test Director' && info.role !== 'Network Support' && info.role !== 'User Support' && info.role !== 'Test Support') {
          socket.emit('userAuthenticated', { success: false, error: 'Invalid role for White Cell team' });
          return;
        }

        if ((info.team === 'red' || info.team === 'blue') && info.role !== 'Mission Lead' && info.role !== 'Analyst' && info.role !== 'Technical Lead') {
          socket.emit('userAuthenticated', { success: false, error: 'Invalid role for team' });
          return;
        }

        if (info.team === 'observer' && info.role !== 'Observer') {
          socket.emit('userAuthenticated', { success: false, error: 'Invalid role for Observer' });
          return;
        }

        // First check if user exists with exact role and team
        const checkResult = await query(
          `SELECT id, username, role, status::varchar(20) as status, team 
           FROM users 
           WHERE username = $1 AND team = $2 AND role = $3`,
          [info.username, info.team, info.role]
        );

        let result;
        if (checkResult.rows.length === 0) {
          // Create new user
          result = await query(
            `INSERT INTO users (username, role, status, team, password_hash, created_at, last_login)
             VALUES ($1, $2, 'online', $3, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
             RETURNING id, username, role, status::varchar(20) as status, team`,
            [info.username, info.role, info.team]
          );
        } else {
          // Update existing user
          result = await query(
            `UPDATE users 
             SET status = 'online', last_login = CURRENT_TIMESTAMP
             WHERE username = $1 AND team = $2 AND role = $3
             RETURNING id, username, role, status::varchar(20) as status, team`,
            [info.username, info.team, info.role]
          );
        }

        if (result.rows.length > 0) {
          userInfo = result.rows[0];
          // Update socket room to include user role
          socket.join(`${userInfo.team}_${userInfo.role}`);
          socket.join(`team_${userInfo.team}`);

          // Add White Cell users to all team rooms
          if (userInfo.team === 'white') {
            logger.info(`White Cell user ${userInfo.id} joined all team rooms`);
            socket.join('team_red');
            socket.join('team_blue');
          }

          logger.info(`Client ${socket.id} (User ${userInfo.id}) joined team ${userInfo.team}`);
          logger.info(`Updated user info for ${socket.id}:`, userInfo);

          // Update socket auth and headers
          const userWithAuth = {
            ...userInfo,
            isAuthenticated: true
          };
          const authData = {
            username: userWithAuth.username,
            team: userWithAuth.team,
            role: userWithAuth.role,
            isAuthenticated: true
          };
          socket.auth = authData;
          socket.handshake.headers['x-helios-username'] = userWithAuth.username;
          socket.handshake.headers['x-helios-team'] = userWithAuth.team;
          socket.handshake.headers['x-helios-role'] = userWithAuth.role;
          socket.handshake.headers['x-helios-authenticated'] = 'true';
          socket.handshake.auth = authData;

          // Update user in database with isAuthenticated flag
          await query(
            `UPDATE users 
             SET is_authenticated = true
             WHERE id = $1
             RETURNING id, username, role, status::varchar(20) as status, team`,
            [userInfo.id]
          );

          // Emit authentication success with isAuthenticated flag
          socket.emit('userAuthenticated', { 
            success: true,
            isAuthenticated: true
          });
        } else {
          logger.error(`Failed to create/update user: ${info.username}`);
          socket.emit('userAuthenticated', { success: false, error: 'Failed to create/update user' });
        }
      } catch (error) {
        logger.error('Error updating user info:', error);
        socket.emit('userAuthenticated', { success: false, error: 'Authentication failed' });
      }
    });

    socket.on('disconnect', () => {
      userInfo = null;
      logger.info(`Client ${socket.id} disconnected`);
    });
  });

  return router;
};
