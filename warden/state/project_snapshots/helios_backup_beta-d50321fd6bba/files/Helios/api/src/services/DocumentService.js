const fs = require('fs').promises;
const path = require('path');
const logger = require('../config/logger');
const multer = require('multer');

class DocumentService {
  constructor() {
    // Use absolute path that matches the volume mount in docker-compose.yml
    this.baseDir = process.env.NODE_ENV === 'production' ? '/usr/src/app/documents' : path.join(__dirname, '../../documents');
    logger.info('DocumentService: Initializing with baseDir:', this.baseDir);
  }

  async initialize() {
    try {
      await this.initializeDirectories();
      this.configureMulter();
      logger.info('DocumentService: Initialization completed successfully');
    } catch (error) {
      logger.error('DocumentService: Initialization failed:', error);
      throw error; // Let the caller handle the error
    }
  }

  async initializeDirectories() {
    try {
      logger.info('DocumentService: Creating base directory:', this.baseDir);
      await fs.mkdir(this.baseDir, { recursive: true });

      const teams = ['red_team', 'blue_team', 'white_cell'];
      for (const team of teams) {
        const teamDir = path.join(this.baseDir, team);
        logger.info('DocumentService: Creating team directory:', teamDir);
        await fs.mkdir(teamDir, { recursive: true });
        
        // Verify directory is writable
        const testFile = path.join(teamDir, '.test');
        await fs.writeFile(testFile, '');
        await fs.unlink(testFile);
      }

      logger.info('Document directories initialized successfully');
    } catch (error) {
      logger.error('Error initializing document directories:', error);
      throw error;
    }
  }

  configureMulter() {
    // Configure multer for file uploads
    this.storage = multer.diskStorage({
      destination: (req, file, cb) => {
        try {
          const team = req.params.team;
          const teamDir = path.join(this.baseDir, this.getTeamDirectory(team));
          logger.info('DocumentService: Setting upload destination:', teamDir);
          cb(null, teamDir);
        } catch (error) {
          logger.error('DocumentService: Error in destination callback:', error);
          cb(error);
        }
      },
      filename: (req, file, cb) => {
        try {
          logger.info('DocumentService: Setting filename:', file.originalname);
          cb(null, file.originalname);
        } catch (error) {
          logger.error('DocumentService: Error in filename callback:', error);
          cb(error);
        }
      }
    });

    this.fileFilter = (req, file, cb) => {
      try {
        if (file.originalname.match(/\.(txt|pdf)$/)) {
          logger.info('DocumentService: File type accepted:', file.originalname);
          cb(null, true);
        } else {
          logger.warn('DocumentService: Invalid file type:', file.originalname);
          cb(new Error('Only .txt and .pdf files are allowed'));
        }
      } catch (error) {
        logger.error('DocumentService: Error in fileFilter:', error);
        cb(error);
      }
    };

    this.upload = multer({
      storage: this.storage,
      fileFilter: this.fileFilter,
      limits: {
        fileSize: 5 * 1024 * 1024 // 5MB limit
      }
    }).single('file');

    logger.info('DocumentService: Multer configuration completed');
  }

  getTeamDirectory(team) {
    const teamMap = {
      'red': 'red_team',
      'blue': 'blue_team',
      'white': 'white_cell'
    };
    const dir = teamMap[team];
    if (!dir) {
      logger.warn('DocumentService: Invalid team directory requested:', team);
    }
    return dir;
  }

  hasAccess(user, targetTeam) {
    // Validate user object and authentication
    if (!user || !user.isAuthenticated) {
      logger.warn('DocumentService: Access denied - User not authenticated');
      return false;
    }

    const { team: userTeam, role: userRole } = user;

    // Validate user has required fields
    if (!userTeam || !userRole) {
      logger.warn('DocumentService: Access denied - Missing user team or role');
      return false;
    }

    // White Cell Operational Test Director has access to all teams
    if (userTeam === 'white' && userRole === 'Operational Test Director') {
      return true;
    }

    // Teams can only access their own documents
    const hasAccess = userTeam === targetTeam;
    if (!hasAccess) {
      logger.warn(`DocumentService: Access denied - User team ${userTeam} cannot access ${targetTeam} documents`);
    }
    return hasAccess;
  }

  handleUpload(req, res) {
    return new Promise((resolve, reject) => {
      try {
        logger.info('DocumentService: Handling file upload');
        this.upload(req, res, (err) => {
          if (err) {
            logger.error('DocumentService: File upload error:', err);
            reject(err);
          } else {
            logger.info('DocumentService: File upload successful');
            resolve();
          }
        });
      } catch (error) {
        logger.error('DocumentService: Error in handleUpload:', error);
        reject(error);
      }
    });
  }

  async listDocuments(user, targetTeam) {
    try {
      logger.info(`DocumentService: Listing documents for team ${targetTeam}`);
      if (!this.hasAccess(user, targetTeam)) {
        throw new Error('Access denied');
      }

      const teamDir = this.getTeamDirectory(targetTeam);
      if (!teamDir) {
        throw new Error('Invalid team');
      }

      const dirPath = path.join(this.baseDir, teamDir);
      const files = await fs.readdir(dirPath);
      
      const fileDetails = await Promise.all(
        files.map(async (file) => {
          const filePath = path.join(dirPath, file);
          const stats = await fs.stat(filePath);
          return {
            name: file,
            size: stats.size,
            modified: stats.mtime
          };
        })
      );

      logger.info(`DocumentService: Found ${fileDetails.length} documents`);
      return fileDetails;
    } catch (error) {
      logger.error('Error listing documents:', error);
      throw error;
    }
  }

  async getDocument(user, targetTeam, filename) {
    try {
      logger.info(`DocumentService: Getting document ${filename} for team ${targetTeam}`);
      if (!this.hasAccess(user, targetTeam)) {
        throw new Error('Access denied');
      }

      const teamDir = this.getTeamDirectory(targetTeam);
      if (!teamDir) {
        throw new Error('Invalid team');
      }

      const filePath = path.join(this.baseDir, teamDir, filename);
      const content = await fs.readFile(filePath, 'utf8');
      logger.info('DocumentService: Document retrieved successfully');
      return content;
    } catch (error) {
      logger.error('Error reading document:', error);
      throw error;
    }
  }

  async shareDocuments(user, documents, targetTeams) {
    try {
      logger.info(`DocumentService: Sharing documents with teams ${targetTeams.join(', ')}`);
      if (!this.hasAccess(user, 'white')) {
        throw new Error('Only White Cell Operational Test Director can share documents');
      }

      const sourceDir = path.join(this.baseDir, this.getTeamDirectory(user.team));

      for (const doc of documents) {
        // Decode the URL encoded filename
        const decodedDoc = decodeURIComponent(doc);
        const sourcePath = path.join(sourceDir, decodedDoc);
        
        // Check if source file exists
        try {
          await fs.access(sourcePath);
        } catch (error) {
          logger.error(`Source file does not exist: ${sourcePath}`);
          throw new Error(`Document "${decodedDoc}" not found in White Cell directory`);
        }

        // Copy to each target team
        for (const targetTeam of targetTeams) {
          const targetDir = path.join(this.baseDir, this.getTeamDirectory(targetTeam));
          const targetPath = path.join(targetDir, decodedDoc);
          
          await fs.copyFile(sourcePath, targetPath);
          logger.info(`Document shared: ${decodedDoc} to ${targetTeam}`);
        }
      }
    } catch (error) {
      logger.error('Error sharing documents:', error);
      throw error;
    }
  }

  async deleteDocument(user, targetTeam, filename) {
    try {
      logger.info(`DocumentService: Deleting document ${filename} from team ${targetTeam}`);
      if (!this.hasAccess(user, targetTeam)) {
        throw new Error('Access denied');
      }

      const teamDir = this.getTeamDirectory(targetTeam);
      if (!teamDir) {
        throw new Error('Invalid team');
      }

      const filePath = path.join(this.baseDir, teamDir, filename);
      await fs.unlink(filePath);
      logger.info(`Document deleted: ${filePath}`);
    } catch (error) {
      logger.error('Error deleting document:', error);
      throw error;
    }
  }
}

// Create singleton instance
const documentService = new DocumentService();

// Export async initialization function
module.exports = {
  initialize: () => documentService.initialize(),
  service: documentService
};
