const logger = require('../config/logger');

const errorHandler = (err, req, res, next) => {
  // Log the error
  logger.error('Error:', {
    message: err.message,
    stack: err.stack,
    path: req.path,
    method: req.method,
    body: req.body,
    query: req.query,
    params: req.params,
    headers: req.headers
  });

  // Handle specific error types
  if (err.name === 'ValidationError') {
    return res.status(400).json({
      error: 'Validation Error',
      details: err.message
    });
  }

  if (err.name === 'UnauthorizedError') {
    return res.status(401).json({
      error: 'Unauthorized',
      details: err.message
    });
  }

  if (err.name === 'ForbiddenError') {
    return res.status(403).json({
      error: 'Forbidden',
      details: err.message
    });
  }

  if (err.name === 'NotFoundError') {
    return res.status(404).json({
      error: 'Not Found',
      details: err.message
    });
  }

  // Handle database connection errors
  if (err.code === 'ECONNREFUSED' && err.message.includes('database')) {
    return res.status(503).json({
      error: 'Database Connection Error',
      details: 'Unable to connect to database'
    });
  }

  // Handle Redis connection errors
  if (err.code === 'ECONNREFUSED' && err.message.includes('redis')) {
    return res.status(503).json({
      error: 'Redis Connection Error',
      details: 'Unable to connect to Redis'
    });
  }

  // Default error response
  const statusCode = err.statusCode || 500;
  const message = process.env.NODE_ENV === 'production' 
    ? 'Internal Server Error'
    : err.message || 'Something went wrong';

  res.status(statusCode).json({
    error: message,
    ...(process.env.NODE_ENV !== 'production' && { stack: err.stack })
  });
};

module.exports = errorHandler;
