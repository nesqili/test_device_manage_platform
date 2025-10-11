#!/bin/bash
echo "Killing Python servers..."
pgrep -f "python" | grep -v $$ | xargs -r kill -9 || echo "No python process found."

echo "Killing Node.js servers..."
pgrep -f "node" | grep -v $$ | xargs -r kill -9 || echo "No node process found."
