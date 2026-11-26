# Rebuilding the map data (optional)

The app ships the processed files, so you never need to run this. It documents where they came from.

```
mkdir /tmp/geo-build && cd /tmp/geo-build
cp <repo>/scripts/geo/* .
npm init -y && npm install mapshaper esbuild d3-geo topojson-client
B=https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson
curl -O $B/ne_50m_admin_0_countries.geojson
curl -O $B/ne_10m_admin_1_states_provinces.geojson
node prep.mjs                 # keep only name, code and label point
mkdir -p out/states
bash build.sh 12% 15%         # simplify (states 12%, world 15%), write out/world.json and out/states/*.json
npx esbuild geo-entry.js --bundle --format=esm --minify --target=es2020 --legal-comments=none --outfile=geo.js
```
Copy `out/world.json` to `app/static/geo/world.json`, `out/states/` to `app/static/geo/states/`, and `geo.js` to `app/static/vendor/geo.js`.
