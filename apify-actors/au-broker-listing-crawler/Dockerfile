FROM apify/actor-node-playwright-chrome:20 AS builder

# The base image already ships a matched Playwright + Chromium pair. Without
# this, installing the "playwright" package pulls down its OWN copy of
# Chromium during the build - doubling browser storage and a likely cause of
# the build running out of disk/memory (observed as npm install exiting 243).
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

COPY package.json package-lock.json* ./
RUN npm install --omit=dev --omit=optional 2>&1 || npm install --omit=dev 2>&1

COPY . ./

CMD ["npm", "start", "--silent"]
