const express = require('express');
const router = express.Router();
const logger = require('../config/logger');
const UserService = require('../services/UserService');

// Set username
router.post('/username', async (req, res) => {
  const { username, team, role } = req.body;

  try {
    console.log('Auth route request body:', { username, team, role });
    logger.debug('Setting username:', { username, team, role });
    const result = await UserService.setUsername(username, team, role);
    
    if (result.success) {
      logger.info('Username set successfully:', { user: result.data });
      const authenticatedUser = {
        ...result.data,
        isAuthenticated: true
      };
      
      // Set auth headers in response
      res.set({
        'x-helios-username': result.data.username,
        'x-helios-team': result.data.team,
        'x-helios-role': result.data.role,
        'x-helios-authenticated': 'true'
      });
      
      console.log('Auth route response:', { authenticatedUser, headers: res.getHeaders() });
      res.json(authenticatedUser);
    } else {
      logger.warn('Failed to set username:', { error: result.error });
      res.status(400).json({ 
        error: result.error,
        details: 'Failed to set username'
      });
    }
  } catch (error) {
    logger.error('Error in /username route:', error);
    res.status(500).json({
      error: 'Internal server error',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// Get user status
router.get('/status/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    logger.debug('Getting user status:', { userId });
    
    const result = await UserService.getStatus(userId);
    
    if (result.success) {
      logger.debug('Got user status:', { status: result.data });
      res.json(result.data);
    } else {
      logger.warn('Failed to get user status:', { error: result.error });
      res.status(404).json({ 
        error: result.error,
        details: 'Failed to get user status'
      });
    }
  } catch (error) {
    logger.error('Error in /status route:', error);
    res.status(500).json({
      error: 'Internal server error',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

// Update user status
router.put('/status/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    const { status } = req.body;
    logger.debug('Updating user status:', { userId, status });

    const result = await UserService.updateStatus(userId, status);
    
    if (result.success) {
      logger.info('User status updated:', { user: result.data });
      res.json(result.data);
    } else {
      logger.warn('Failed to update user status:', { error: result.error });
      res.status(400).json({ 
        error: result.error,
        details: 'Failed to update user status'
      });
    }
  } catch (error) {
    logger.error('Error in /status update route:', error);
    res.status(500).json({
      error: 'Internal server error',
      details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
  }
});

module.exports = router;
