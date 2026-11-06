# Development server for the local Compose stack. Production uses `npm run build` and a static host.
FROM node:22-slim

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]
