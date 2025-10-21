# frontend/Dockerfile

# Use an official Node.js runtime as a parent image
FROM node:20-alpine

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy package.json and package-lock.json (or yarn.lock)
COPY package*.json ./

# Install project dependencies
RUN npm install

# Copy the rest of the application's source code
COPY . .

# Your app runs on port 5173 inside the container
EXPOSE 5173

# The command to start the app (will be overridden by docker-compose)
CMD ["npm", "run", "dev"]