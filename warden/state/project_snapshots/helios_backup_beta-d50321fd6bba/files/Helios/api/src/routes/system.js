const express = require('express');
const os = require('os');
const router = express.Router();

function getServerIP() {
    const networkInterfaces = os.networkInterfaces();
    let serverIP = 'localhost';

    // Look through all network interfaces
    for (const interfaceName of Object.keys(networkInterfaces)) {
        const interface = networkInterfaces[interfaceName];
        // Skip internal/loopback interfaces
        if (!interface) continue;

        for (const config of interface) {
            // Look for IPv4, non-internal addresses
            if (config.family === 'IPv4' && !config.internal) {
                serverIP = config.address;
                break;
            }
        }
        if (serverIP !== 'localhost') break;
    }

    return serverIP;
}

// Endpoint to get server information including IP
router.get('/info', (req, res) => {
    const serverIP = getServerIP();
    res.json({
        ip: serverIP,
        port: process.env.PORT || 3000,
        wsPort: process.env.WS_PORT || 3000,
        environment: process.env.NODE_ENV || 'development'
    });
});

module.exports = router;
