FROM node:20-alpine

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json* /app/
RUN npm install

COPY apps/web /app

EXPOSE 3000
CMD ["npx", "next", "dev", "--hostname", "0.0.0.0", "--port", "3000"]
