#!/usr/bin/env bash
set -e
STATES=${1:-12%}; WORLD=${2:-15%}
npx mapshaper countries.prep.geojson -simplify $WORLD keep-shapes -o out/world.json format=topojson quantization=10000 >/dev/null 2>&1
npx mapshaper states.prep.geojson -simplify $STATES keep-shapes -o states.simplified.geojson format=geojson precision=0.0001 >/dev/null 2>&1
node split.mjs $STATES
echo "world: $(du -k out/world.json | cut -f1)KB   states total: $(du -sk out/states | cut -f1)KB   files: $(ls out/states | wc -l)"
