const express = require('express');
const router = express.Router();
const logger = require('../config/logger');

module.exports = (chatService) => {
  // Share document with team(s)
  router.post('/share-document', async (req, res) => {
    try {
      const { documentId, targetTeam, senderId } = req.body;
      logger.debug('Sharing document:', { documentId, targetTeam, senderId });

      // Create a system message for the document share
      const message = {
        sender: {
          id: senderId,
          username: 'System'
        },
        content: `Shared document: ${documentId}`,
        team: 'white',
        targetTeam,
        timestamp: new Date().toISOString()
      };

      const result = await chatService.handleNewMessage(message);
      if (result) {
        logger.info('Document shared successfully:', { documentId, targetTeam });
        res.json({ success: true, message: result });
      } else {
        logger.warn('Failed to share document:', { documentId, targetTeam });
        res.status(400).json({ 
          success: false,
          error: 'Failed to share document'
        });
      }
    } catch (error) {
      logger.error('Error in share-document route:', error);
      res.status(500).json({
        success: false,
        error: 'Internal server error'
      });
    }
  });

  // Get chat history for a mission
  router.get('/history/:missionId', async (req, res) => {
    try {
      const { missionId } = req.params;
      const result = await chatService.getChatHistory(missionId);
      if (result.success) {
        res.json(result.data);
      } else {
        res.status(500).json({ error: result.error });
      }
    } catch (error) {
      logger.error('Error in chat history route:', error);
      res.status(500).json({ error: 'Internal server error' });
    }
  });

  return router;
};
