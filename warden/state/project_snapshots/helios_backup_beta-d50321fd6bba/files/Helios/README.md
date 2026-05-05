# Helios

A full-stack application with Node.js backend and React/TypeScript frontend.

## System Requirements

- Node.js >= 18.x
- PostgreSQL >= 14.x
- Redis >= 6.x
- Nginx >= 1.20

## Backend Dependencies

Core dependencies:
- Express.js - Web framework
- Socket.IO - Real-time communication
- PostgreSQL (pg) - Database
- Redis - Caching and session management
- JWT - Authentication
- Winston - Logging
- Bcrypt - Password hashing
- Helmet - Security middleware
- CORS - Cross-origin resource sharing
- Joi - Data validation

Development dependencies:
- Jest - Testing
- Nodemon - Development server
- Supertest - HTTP testing

## Frontend Dependencies

Core dependencies:
- React 18
- TypeScript
- Chakra UI - Component library
- Axios - HTTP client
- Socket.IO Client - Real-time communication
- React Router - Routing
- Framer Motion - Animations
- TailwindCSS - Styling
- Lucide React - Icons

Development dependencies:
- Vite - Build tool
- TypeScript types (@types/*)
- PostCSS/Autoprefixer - CSS processing

## Setup Instructions

1. Install system dependencies:
   - Node.js
   - PostgreSQL
   - Redis
   - Nginx

2. Backend setup:
   ```bash
   cd api
   npm install
   ```

3. Frontend setup:
   ```bash
   cd frontend
   npm install
   ```

4. Environment configuration:
   - Copy `.env.example` to `.env`
   - Configure database credentials
   - Configure Redis connection
   - Set JWT secret

5. Database setup:
   - Create PostgreSQL database
   - Run schema migrations

6. Start development servers:
   - Backend: `npm run dev` in /api
   - Frontend: `npm run dev` in /frontend

## Docker Deployment

### Prerequisites
- Docker Desktop for Windows
- WSL2 enabled
- Git for Windows

### Environment Setup
1. Copy `.env.example` to `.env` and configure:
   ```
   DATABASE_URL=postgresql://postgres:postgres@db:5432/helios
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_DB=helios
   JWT_SECRET=your-secret-key
   JWT_EXPIRATION=24h
   REDIS_URL=redis://redis:6379
   ```

### Building and Running Containers
1. Open Docker Desktop and ensure it's running
2. Open PowerShell or Command Prompt in the project directory
3. Build and start containers:
   ```powershell
   # PowerShell commands
   Set-Location -Path Helios
   docker-compose down -v           # Clean up any existing containers and volumes
   docker-compose build --no-cache  # Fresh build of images
   docker-compose up -d            # Start containers in detached mode
   ```
   ```cmd
   # Command Prompt
   cd Helios
   docker-compose down -v
   docker-compose build --no-cache
   docker-compose up -d
   ```

### Verifying Services
1. Check container status:
   ```cmd
   docker-compose ps
   ```
2. View logs:
   ```cmd
   docker-compose logs -f          # Follow all logs
   docker-compose logs -f api      # Follow API logs only
   ```

### Container Details
- Database (PostgreSQL 14)
  - Port: 5432
  - Data persistence: postgres_data volume
  - Health check enabled

- API (Node.js 18)
  - Port: 3001
  - Documents stored in documents_data volume
  - Waits for database before starting
  - Health check enabled

- Redis (v7)
  - Port: 6379
  - Data persistence: redis_data volume

### Troubleshooting
1. Port Conflicts
   - Ensure ports 3001, 5432, and 6379 are not in use
   - Stop any local PostgreSQL/Redis instances

2. Database Connection Issues
   - Check if database container is healthy:
     ```cmd
     docker-compose ps db
     ```
   - View database logs:
     ```cmd
     docker-compose logs db
     ```

3. Volume Issues
   - If schema isn't loading, try removing volumes:
     ```cmd
     docker-compose down -v
     docker-compose up -d
     ```

4. Container Build Issues
   - Try rebuilding without cache:
     ```cmd
     docker-compose build --no-cache
     ```
   - Check Docker Desktop has sufficient resources

### Maintenance
- Backup Volumes:
  ```cmd
  docker run --rm -v helios_postgres_data:/source -v %cd%:/backup alpine tar -czf /backup/postgres_backup.tar.gz -C /source ./
  ```
- Restore Volumes:
  ```cmd
  docker run --rm -v helios_postgres_data:/target -v %cd%:/backup alpine sh -c "cd /target && tar -xzf /backup/postgres_backup.tar.gz"
  ```
