FROM apify/actor-node-playwright-chrome:20 AS builder

# The base image already ships a matched Playwright + Chromium pair. Without
# this, installing the "playwright" package would pull down its OWN copy of
# Chromium during the build, doubling browser storage for no reason.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# The base image runs as the non-root user "myuser" (home: /home/myuser).
# COPY writes as root by default regardless of the active USER, so without
# --chown the copied files are root-owned and "npm install" (running as
# myuser) can't write package-lock.json - fails with EACCES.
COPY --chown=myuser:myuser package.json package-lock.json* ./
RUN npm install --omit=dev --omit=optional 2>&1 || npm install --omit=dev 2>&1

COPY --chown=myuser:myuser . ./

CMD ["npm", "start", "--silent"]
