FROM node:20-slim

WORKDIR /app

# Copy files and install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy application source
COPY . .

EXPOSE 5173

# Run Vite in host mode so it's accessible externally
CMD ["npm", "run", "dev", "--", "--host"]
