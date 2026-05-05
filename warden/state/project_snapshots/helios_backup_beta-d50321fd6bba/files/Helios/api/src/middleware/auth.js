const { query } = require('../config/database');
const { logError } = require('../config/logger');

const authMiddleware = async (req, res, next) => {
    try {
        // Debug log the request path and method
        console.log('Auth middleware request:', {
            path: req.path,
            baseUrl: req.baseUrl,
            originalUrl: req.originalUrl,
            method: req.method
        });

        // Skip validation for initial login
        if ((req.path === '/username' || req.originalUrl === '/api/auth/username') && req.method === 'POST') {
            return next();
        }

        // Get username from custom header, socket handshake auth, or socket request
        let username = req.headers?.['x-helios-username'];
        let team = req.headers?.['x-helios-team'];
        let role = req.headers?.['x-helios-role'];
        let isAuthenticated = req.headers?.['x-helios-authenticated'] === 'true';

        // For socket requests, check socket auth
        if (req.socket?.handshake) {
            const socketTeam = req.socket.handshake.headers['x-helios-team'] || 
                             req.socket.handshake.auth?.team;
            const socketRole = req.socket.handshake.headers['x-helios-role'] || 
                             req.socket.handshake.auth?.role;
            const socketAuth = req.socket.handshake.headers['x-helios-authenticated'] === 'true' || 
                             req.socket.handshake.auth?.isAuthenticated === true;
            
            if (socketTeam && socketRole) {
                team = socketTeam;
                role = socketRole;
                req.isAuthenticated = socketAuth;
            }
        }

        // For socket.io requests, check socket.request
        if (req.socket?.request) {
            const requestTeam = req.socket.request.headers['x-helios-team'];
            const requestRole = req.socket.request.headers['x-helios-role'];
            const requestAuth = req.socket.request.headers['x-helios-authenticated'] === 'true';

            if (requestTeam && requestRole) {
                team = requestTeam;
                role = requestRole;
                if (requestAuth) {
                    req.isAuthenticated = true;
                }
            }
        }

        // For socket.io requests, check socket.request.auth
        if (req.socket?.request?.auth) {
            const authTeam = req.socket.request.auth.team;
            const authRole = req.socket.request.auth.role;
            const authFlag = req.socket.request.auth.isAuthenticated === true;

            if (authTeam && authRole) {
                team = authTeam;
                role = authRole;
                if (authFlag) {
                    req.isAuthenticated = true;
                }
            }
        }

        // For socket.io requests, check socket.request.headers
        if (req.socket?.request?.headers) {
            const headerTeam = req.socket.request.headers['x-helios-team'];
            const headerRole = req.socket.request.headers['x-helios-role'];

            if (headerTeam && headerRole) {
                team = headerTeam;
                role = headerRole;
            }
        }
        
        // For socket requests, get username from socket
        if (req.socket?.handshake) {
            const socketUsername = req.socket.handshake.headers['x-helios-username'] || 
                                 req.socket.handshake.auth?.username;
            if (socketUsername) {
                username = socketUsername;
            }
        }

        // For socket.io requests, check socket.request
        if (req.socket?.request) {
            const requestUsername = req.socket.request.headers['x-helios-username'];
            if (requestUsername) {
                username = requestUsername;
            }
        }

        // For socket.io requests, check socket.request.auth
        if (req.socket?.request?.auth) {
            const authUsername = req.socket.request.auth.username;
            if (authUsername) {
                username = authUsername;
            }
        }

        // For socket.io requests, check socket.request.headers
        if (req.socket?.request?.headers) {
            const headerUsername = req.socket.request.headers['x-helios-username'];
            if (headerUsername) {
                username = headerUsername;
            }
        }

        // If no username found but we have team and role, generate a temporary one
        if (!username && team && role) {
            username = `${team}_${role}_${Date.now()}`;
        }

        if (!team || !role) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Team and role are required'
            });
        }

        // Validate team and role combinations
        if (team === 'white' && role !== 'Operational Test Director' && role !== 'Network Support' && role !== 'User Support' && role !== 'Test Support') {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Invalid role for White Cell team'
            });
        }

        if ((team === 'red' || team === 'blue') && role !== 'Mission Lead' && role !== 'Analyst' && role !== 'Technical Lead') {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Invalid role for team'
            });
        }

        if (team === 'observer' && role !== 'Observer') {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Invalid role for Observer'
            });
        }

        // First check if user exists with exact role and team
        const checkResult = await query(
            `SELECT id, username, role, status::varchar(20) as status, team 
             FROM users 
             WHERE username = $1 AND team = $2 AND role = $3`,
            [username, team, role]
        );

        let userResult;
        if (checkResult.rows.length === 0) {
            // Create new user
            userResult = await query(
                `INSERT INTO users (username, role, status, team, password_hash, created_at, last_login, is_authenticated)
                 VALUES ($1, $2, 'online', $3, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, true)
                 RETURNING id, username, role, status::varchar(20) as status, team, is_authenticated`,
                [username, role, team]
            );
        } else {
            // Update existing user
            userResult = await query(
                `UPDATE users 
                 SET role = $2, team = $3, status = 'online', password_hash = NULL, last_login = CURRENT_TIMESTAMP, is_authenticated = true
                 WHERE username = $1
                 RETURNING id, username, role, status::varchar(20) as status, team, is_authenticated`,
                [username, role, team]
            );
        }

        if (userResult.rows.length === 0) {
            return res.status(401).json({
                error: 'Unauthorized',
                message: 'Failed to authenticate user'
            });
        }

        // Add user info to request, ensuring isAuthenticated is set from all possible sources
        req.user = {
            id: userResult.rows[0].id,
            username: userResult.rows[0].username,
            role: userResult.rows[0].role,
            status: userResult.rows[0].status,
            team: userResult.rows[0].team,
            isAuthenticated: isAuthenticated || 
                           userResult.rows[0].is_authenticated || 
                           req.isAuthenticated ||
                           (req.socket?.handshake?.auth?.isAuthenticated === true) ||
                           (req.socket?.request?.auth?.isAuthenticated === true) ||
                           false
        };

        next();
    } catch (error) {
        logError('Auth middleware error:', { error });
        res.status(500).json({
            error: 'Internal server error',
            message: 'Authentication failed'
        });
    }
};

module.exports = authMiddleware;
