const logger = require('../config/logger');
const db = require('../config/database');

class ChatService {
  constructor(io) {
    this.io = io;
    this.HISTORY_LIMIT = 50;
    this.activeUsers = new Map(); // Store active users with their socket IDs
    this.initialized = false;
  }

  async updateUserStatus(userId, status) {
    try {
      await db.query(
        `UPDATE users 
         SET status = $1::varchar(20)
         WHERE id = $2`,
        [status, userId]
      );
      logger.debug(`Updated user ${userId} status to ${status}`);
    } catch (error) {
      logger.error('Error updating user status:', error);
    }
  }

  async initialize() {
    if (this.initialized) {
      return;
    }

    try {
      // Test database connection before setting up socket handlers
      const testResult = await db.query('SELECT NOW()');
      if (!testResult) {
        throw new Error('Database connection test failed');
      }
      logger.info('ChatService: Database connection test successful');

      this.setupSocketHandlers();
      this.initialized = true;
      logger.info('ChatService: Initialization completed successfully');
    } catch (error) {
      logger.error('ChatService: Initialization failed:', error);
      throw error;
    }
  }

  setupSocketHandlers() {
    this.io.on('connection', (socket) => {
      logger.info(`Client connected: ${socket.id}`);

      // Handle joining team chat rooms
      socket.on('joinTeam', async ({ team, userId }) => {
        try {
          // Get user data from database
          const result = await db.query(
            'SELECT username, role, status FROM users WHERE id = $1',
            [userId]
          );
          
          if (result.rows.length === 0) {
            logger.error(`User not found: ${userId}`);
            return;
          }

          const user = {
            id: userId,
            username: result.rows[0].username,
            role: result.rows[0].role,
            status: 'online',
            team,
            socketId: socket.id
          };

          // Store user data
          this.activeUsers.set(socket.id, user);

          // Update user status in database
          await this.updateUserStatus(userId, 'online');

          // Leave previous rooms
          Object.keys(socket.rooms).forEach(room => {
            if (room !== socket.id) {
              socket.leave(room);
            }
          });

          // Join team room
          socket.join(`team:${team}`);
          logger.info(`Client ${socket.id} (User ${userId}) joined team ${team}`);

          // If White Cell, also join both team rooms
          if (team === 'white') {
            socket.join('team:red');
            socket.join('team:blue');
            logger.info(`White Cell user ${userId} joined all team rooms`);
          }

          // Send chat history for this team
          const history = await this.getTeamMessages(team);
          socket.emit('chatHistory', history);

          // If White Cell, send both team histories
          if (team === 'white') {
            const redHistory = await this.getTeamMessages('red');
            const blueHistory = await this.getTeamMessages('blue');
            socket.emit('redTeamHistory', redHistory);
            socket.emit('blueTeamHistory', blueHistory);
          }

          // Notify others of new user
          socket.broadcast.emit('userJoined', user);

          // Send active users list to the new user
          const activeUsersList = Array.from(this.activeUsers.values());
          socket.emit('activeUsers', activeUsersList);
        } catch (error) {
          logger.error('Error joining team:', error);
        }
      });

      // Handle get active users request
      socket.on('getActiveUsers', () => {
        const activeUsersList = Array.from(this.activeUsers.values());
        socket.emit('activeUsers', activeUsersList);
      });

      // Handle status updates
      socket.on('updateStatus', async (status) => {
        const user = this.activeUsers.get(socket.id);
        if (user) {
          user.status = status;
          this.activeUsers.set(socket.id, user);
          await this.updateUserStatus(user.id, status);
          this.io.emit('userStatusUpdate', { userId: user.id, status });
        }
      });

      // Handle new messages
      socket.on('sendMessage', async (message) => {
        try {
          logger.info(`Received message from ${message.sender.username} (${message.sender.id}) for team ${message.team}`);
          const savedMessage = await this.handleNewMessage(message);
          logger.info(`Successfully saved message: ${JSON.stringify(savedMessage)}`);
          
          // Broadcast to appropriate team room
          logger.debug(`Broadcasting message to team rooms. Message team: ${message.team}, Target team: ${message.targetTeam}`);
          if (message.team === 'red') {
            this.io.to('team:red').emit('chatMessage', savedMessage);
            // Also send to White Cell
            this.io.to('team:white').emit('redTeamMessage', savedMessage);
          } else if (message.team === 'blue') {
            this.io.to('team:blue').emit('chatMessage', savedMessage);
            // Also send to White Cell
            this.io.to('team:white').emit('blueTeamMessage', savedMessage);
          } else if (message.team === 'white') {
            // If targetTeam is null or undefined, treat as broadcast
            if (!message.targetTeam) {
              logger.info('Broadcasting white team message to all teams');
              // Broadcast to all teams
              this.io.to('team:red').emit('chatMessage', savedMessage);
              this.io.to('team:blue').emit('chatMessage', savedMessage);
              this.io.to('team:white').emit('chatMessage', savedMessage);
              // Also send to white cell's team-specific channels
              this.io.to('team:white').emit('redTeamMessage', savedMessage);
              this.io.to('team:white').emit('blueTeamMessage', savedMessage);
            } else if (message.targetTeam === 'red') {
              logger.info('Sending white team message to red team');
              this.io.to('team:red').emit('chatMessage', savedMessage);
              this.io.to('team:white').emit('redTeamMessage', savedMessage);
            } else if (message.targetTeam === 'blue') {
              logger.info('Sending white team message to blue team');
              this.io.to('team:blue').emit('chatMessage', savedMessage);
              this.io.to('team:white').emit('blueTeamMessage', savedMessage);
            }
          }
        } catch (error) {
          logger.error('Error handling message:', error);
        }
      });

      // Handle message delivery confirmation
      socket.on('messageDelivered', async (messageId) => {
        try {
          await this.markMessageDelivered(messageId);
          logger.debug(`Message ${messageId} marked as delivered`);
        } catch (error) {
          logger.error('Error marking message as delivered:', error);
        }
      });

      // Handle disconnection
      socket.on('disconnect', async () => {
        const user = this.activeUsers.get(socket.id);
        if (user) {
          // Update user status to "SIGNED OUT"
          await this.updateUserStatus(user.id, 'SIGNED OUT');
          this.io.emit('userStatusUpdate', { userId: user.id, status: 'SIGNED OUT' });
          this.io.emit('userLeft', user.id);
          this.activeUsers.delete(socket.id);
        }
        logger.info(`Client disconnected: ${socket.id}`);
      });
    });
  }

  async markMessageDelivered(messageId) {
    try {
      await db.query(
        `UPDATE chat_messages 
         SET delivered_at = CURRENT_TIMESTAMP 
         WHERE id = $1 AND delivered_at IS NULL`,
        [messageId]
      );
    } catch (error) {
      logger.error('Error updating message delivery status:', error);
      throw error;
    }
  }

  async handleNewMessage(message) {
    try {
      // Ensure timestamp is a valid Date object
      const timestamp = message.timestamp ? new Date(message.timestamp) : new Date();
      
      // Format timestamp as ISO string for consistent storage
      const formattedTimestamp = timestamp.toISOString();

      logger.debug(`Saving message to database: ${JSON.stringify(message)}`);
      
      // Store message in database with sent timestamp
      const result = await db.query(
        `INSERT INTO chat_messages (sender_id, content, team, target_team, created_at, sent_at) 
         VALUES ($1, $2, $3, $4, $5, $6) 
         RETURNING id, content, team, target_team, created_at as timestamp, sent_at, delivered_at`,
        [message.sender.id, message.content, message.team, message.targetTeam, formattedTimestamp, formattedTimestamp]
      );

      logger.debug(`Database query result: ${JSON.stringify(result.rows[0])}`);
      
      const savedMessage = {
        id: result.rows[0].id,
        content: result.rows[0].content,
        team: result.rows[0].team,
        targetTeam: result.rows[0].target_team,
        timestamp: new Date(result.rows[0].timestamp).toISOString(),
        sent_at: new Date(result.rows[0].sent_at).toISOString(),
        delivered_at: result.rows[0].delivered_at ? new Date(result.rows[0].delivered_at).toISOString() : null,
        sender: message.sender
      };

      logger.debug(`Saved message: ${JSON.stringify(savedMessage)}`);
      return savedMessage;
    } catch (error) {
      logger.error('Error saving message:', error);
      throw error;
    }
  }

  async getTeamMessages(team) {
    try {
      logger.info(`Fetching messages for team: ${team}`);
      const result = await db.query(
        `SELECT 
          cm.id, 
          cm.content, 
          cm.created_at as timestamp,
          cm.team,
          cm.target_team,
          cm.sent_at,
          cm.delivered_at,
          u.id as "sender.id",
          u.username as "sender.username"
         FROM chat_messages cm 
         JOIN users u ON cm.sender_id = u.id 
         WHERE (cm.team = $1 OR (cm.team = 'white' AND cm.target_team = $1))
         ORDER BY cm.created_at ASC 
         LIMIT $2`,
        [team, this.HISTORY_LIMIT]
      );

      logger.debug(`Found ${result.rows.length} messages for team ${team}`);
      
      // Format timestamps and include target team in the response
      const messages = result.rows.map(row => ({
        id: row.id,
        content: row.content,
        team: row.team,
        targetTeam: row.target_team,
        timestamp: new Date(row.timestamp).toISOString(),
        sent_at: row.sent_at ? new Date(row.sent_at).toISOString() : null,
        delivered_at: row.delivered_at ? new Date(row.delivered_at).toISOString() : null,
        sender: {
          id: row['sender.id'],
          username: row['sender.username']
        }
      }));
      
      logger.debug(`Formatted messages for team ${team}: ${JSON.stringify(messages)}`);
      return messages;
    } catch (error) {
      logger.error('Error fetching messages:', error);
      throw error;
    }
  }

  // Method to get chat history
  async getChatHistory(team) {
    try {
      const messages = await this.getTeamMessages(team);
      return {
        success: true,
        data: messages
      };
    } catch (error) {
      logger.error('Error getting chat history:', error);
      return {
        success: false,
        error: 'Failed to get chat history'
      };
    }
  }
}

module.exports = ChatService;
