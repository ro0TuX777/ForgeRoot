const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Create nginx/ssl directory if it doesn't exist
const sslDir = path.join(__dirname, 'nginx', 'ssl');
if (!fs.existsSync(sslDir)) {
    fs.mkdirSync(sslDir, { recursive: true });
}

// Generate self-signed certificate
console.log('Generating self-signed SSL certificate...');
try {
    execSync(`openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout ${path.join(sslDir, 'key.pem')} \
        -out ${path.join(sslDir, 'cert.pem')} \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"`, 
        { stdio: 'inherit' }
    );
    console.log('SSL certificate generated successfully!');
} catch (error) {
    console.error('Error generating SSL certificate:', error);
    process.exit(1);
}
