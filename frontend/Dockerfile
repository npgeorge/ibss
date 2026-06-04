FROM node:18-alpine

# Set working directory
WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
# react-scripts@5 declares a peerOptional on typescript ^3||^4 while the app
# pins typescript ^5; npm 10's strict peer resolver errors on that, so accept
# the (working) resolution explicitly.
RUN npm install --legacy-peer-deps

# Copy application
COPY . .

# Expose port
EXPOSE 3000

# Start application
CMD ["npm", "start"]
