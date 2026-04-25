FROM node:20-alpine

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json* /app/
RUN npm install

COPY apps/web /app

# Build for production (standalone output mode is already set in next.config.js)
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
