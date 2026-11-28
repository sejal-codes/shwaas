# Urban Air Quality Assistant

A GenAI-powered assistant that helps families navigate severe winter smog. It estimates
the air inside your home, ranks the fixes that matter most, and gives plan-specific advice
that weighs both your exposure and the pollution you add for everyone else.

> Status: complete: rule engine, live air data, Gemini layer, JSON API and an accessible English/Hindi web UI, all tested.

## Chosen vertical
Challenge 6: Urban Air Quality Assistant (families and communities in severe winter smog).

## Approach
Two layers, kept deliberately separate:

1. **Rule engine (plain Python, fully unit tested)** makes every decision: indoor estimate,
   ranked fixes, travel-mode ranking, mask level, timing. Same input, same output.
2. **GenAI layer (Gemini, coming next)** turns the user's free-text plan into structured data,
   asks one follow-up when the plan is vague, and explains the rule engine's results in friendly
   language (including Hindi). It explains the numbers; it never invents them.

## The experience
1. **A conversation about your household.** A text box asks "Who lives in your home?" and understands natural answers
   ("Only me", "Me and my parents", "Me and my family"). If you live alone nothing more is asked; if you mention family
   without saying whether there are children or elderly people, it asks exactly that, and only what is still missing.
2. **A globe, then a map.** When you scroll to the location section a real 3D globe appears. Rotate it, zoom, tap a country; it
   flies in and cross-fades into a flat map of that country with every state or province as a selectable shape.
   Your country and state are saved as the location. A search box does the same by keyboard, and typing a city or sharing
   device location still work.
3. **Quick taps** for windows, cooking, heating and "do you have an air purifier?", each gliding to the next question.

## How it works
1. User answers a few profile questions (who is at home, windows, cooking, heating, purifier).
2. App shows outdoor AQI, an **estimated** indoor score with the reasons, and the top 3 fixes.
3. A text box asks "Planning something?". Advice appears only for what the user types.
4. The user marks timing as **Fixed** or **Flexible**. Better-time suggestions appear only for Flexible.
5. Travel advice picks the lowest-emission option that is still safe for that person; a private
   car is only a flagged fallback.

## Safety rules built into the logic
- Essential activities (school, work, medical) are never skipped or postponed.
- Optional activities (exercise, leisure) may get an indoor alternative in bad air.
- Indoor values are labelled estimates. The app gives general guidance, not medical advice.
- All input is validated and rejected if malformed.

## Assumptions
- Parents, grandparents and in-laws are treated as older adults. If children and older adults both live at home, the stricter
  older-adult rules are used. A household that lists its members explicitly is assumed to have no one it did not mention.
- Air quality for a picked state is read at that state's label point (a representative point inside it), so it is a regional
  figure, not a street-level one.
Extra-care tips (spend less time outside, before and after, recovery) appear only when the air is above the mask threshold; in clean air they are skipped.
Children are assumed to travel only on a school run. On any other plan, a family household's traveller is treated as an adult;
older-adult households keep their stricter rules on every plan.
All tunable numbers (infiltration, source strengths, mode speeds, CO2 per km, mask effect) live in
`app/assumptions.py` and are rough, illustrative estimates, not measurements. PM2.5 is converted to
the Indian NAQI using CPCB bands, applied to the reading we have (CPCB uses 24-hour averages).

## Accessibility and inclusive design
- Fully keyboard operable, with a skip link, visible focus rings and real `<label>`/`<fieldset>`/`<legend>` markup.
- Screen-reader friendly: live regions for status and errors, the AQI gauge has a text alternative, and meaning is never carried by colour alone (every severity shows a text label).
- Text contrast meets WCAG AA (4.5:1) in both dark and light mode; this is enforced by a test that reads the real CSS.
- Large tap targets (at least 44px), responsive layout, and system fonts that render Hindi.
- Respects `prefers-reduced-motion`, `prefers-color-scheme` and forced-colors mode.
- English and Hindi (labels, results and the AI explanation). The practical tip lists are currently English-only; the UI says so in Hindi mode.
- Works without a Gemini key: if the AI is offline the user picks their plan from a plain form.

## Security and efficiency
- Strict input validation everywhere; request size cap, JSON-only bodies, per-client rate limit.
- Gemini key is read from the environment (never committed) and sent in a header, never in a URL.
- User text is length-capped, cleaned, wrapped as data, and Gemini's JSON is re-validated before use.
- Security headers (CSP, nosniff, no-referrer) and no stack traces in responses.
- The UI has no inline scripts or styles, no third-party resources and no storage (no cookies, localStorage or analytics).
  Server and AI text is inserted as text, never as HTML, and a test proves it.
- Device location is optional and rounded to 2 decimals before it leaves the browser.
- Live AQI and geocoding are cached with a TTL and a size cap, so repeat requests cost nothing.
- If a Gemini model is overloaded, rate limited or slow, the next model is tried (with per-attempt and total time limits).
  If every model fails, Gemini is paused for 30 seconds so users get instant rule-based answers instead of waiting.
- If Gemini is down, rule-based template text is used and the app keeps working.

## API
- `GET /api/health`
- `POST /api/assess` with `{home, location: {city} or {latitude, longitude}, language}`
- `POST /api/plan` with `{home, location, timing: "fixed"|"flexible", plan_text}` or a structured `plan`

## Real monitor data (optional)
By default the outdoor figure is an estimate from an atmospheric model (Open-Meteo). Set a free `OPENAQ_API_KEY`
(explore.openaq.org/register) and the app uses the nearest real monitor within 25 km that reported in the last 3 hours,
and says which station, how far and how old. If there is none, it falls back to the model and says so. The index is
India's 0-500 NAQI computed from PM2.5, and the page shows the PM2.5 in µg/m³ next to it.
Check what monitors exist near a place with `python -m scripts.check_openaq 14.37 75.67`.

## Deploying to the web
The app runs under gunicorn (`Procfile` and `Dockerfile` are included). Set `GEMINI_API_KEY` (and optionally `OPENAQ_API_KEY`)
as environment variables on the host, plus `TRUST_PROXY=1` so rate limiting sees each visitor, not the host's proxy.
- **Render (free):** New Web Service, connect the repo, build `pip install -r requirements.txt`,
  start `gunicorn "app.server:create_app()" --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60`.
- **Google Cloud Run:** `gcloud run deploy shwaas --source . --region asia-south1 --allow-unauthenticated --set-env-vars TRUST_PROXY=1`
  (then add the keys as environment variables or Secret Manager secrets).
Health check: `/api/health`.

## Configuration
Set `GEMINI_API_KEY` as an environment variable or Codespaces secret. Optionally set `GEMINI_MODEL` to a comma-separated
list of model names (tried in order; the default is a fail-over chain of four).
Without a key the app runs in template mode. Air data comes from Open-Meteo (no key needed).

## Map data and third-party code
Country and state/province boundaries come from Natural Earth (public domain), simplified for the web (about 2.6 MB for all
242 countries, loaded one country at a time). The globe and map use a 36 KB bundle of d3-geo and topojson-client (ISC licence).
Details are in `app/static/vendor/NOTICE.txt` and `scripts/geo/README.md`.

## Project layout
```
app/
  models.py       validated data models and enums
  assumptions.py  every tunable number, in one place
  aqi.py          PM2.5 -> NAQI, severity, alert
  indoor.py       indoor estimate and ranked fixes
  travel.py       exposure + emissions mode ranking
  timing.py       best-time suggestion (flexible plans only)
  activity.py     combines everything into plan advice
  air_data.py     Open-Meteo geocoding + live/hourly PM2.5 (cached)
  gemini.py       minimal Gemini REST client
  ai.py           plan parsing, clarifying question, explanations (+ fallbacks)
  explain.py      template explanations used when Gemini is unavailable
  service.py      orchestrates one request end to end
  server.py       Flask API with limits and security headers; also serves the UI
  static/         index.html, styles.css, i18n.json (EN/HI), app.js and its modules:
                  household.js (understands who lives at home), chat.js, globe.js, flatmap.js, core.js, location.js,
                  quick.js, scroll.js, motion.js, plus geo/ (map data) and vendor/ (d3-geo bundle)
  cache.py, ratelimit.py, config.py
tests/            pytest suite (no test touches the network) + tests/js browser-behaviour tests
```

## Run
```
pip install -r requirements.txt
pytest                      # run the tests
python -m app.server        # start the app on port 5000, then open it in the browser
```
To see which Gemini models work for your key: `python -m scripts.check_gemini`.

Optional browser-behaviour tests (jsdom, needs Node):
```
npm install && npm test
```
If the API response shape ever changes, refresh the UI fixtures with `python -m tests.js_fixtures`.
