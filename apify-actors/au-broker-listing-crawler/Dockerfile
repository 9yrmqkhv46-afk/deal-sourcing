FROM apify/actor-node-playwright-chrome:20 AS builder

COPY package.json package-lock.json* ./
RUN npm install --omit=dev --omit=optional 2>&1 || npm install --omit=dev 2>&1

COPY . ./

CMD ["npm", "start", "--silent"]
