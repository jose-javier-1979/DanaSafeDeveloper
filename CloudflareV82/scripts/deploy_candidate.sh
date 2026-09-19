#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
command -v node >/dev/null 2>&1 || { echo "Node.js is required"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker Desktop/Colima is required for the Container build"; exit 1; }
cd CloudflareV82
npm install
npx wrangler r2 bucket create danasafe-radar-v82-candidate >/dev/null 2>&1 || true
npx wrangler deploy --config wrangler.jsonc
