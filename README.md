# Urban Air Quality Assistant

A GenAI-powered assistant that helps families navigate severe winter smog. It estimates
the air inside your home, ranks the fixes that matter most, and gives plan-specific advice
that weighs both your exposure and the pollution you add for everyone else.

> Status: rule engine, live air data, Gemini layer and JSON API complete and tested. UI is next.

## Chosen vertical
Challenge 6: Urban Air Quality Assistant (families and communities in severe winter smog).

## Approach
Two layers, kept deliberately separate:

1. **Rule engine (plain Python, fully unit tested)** makes every decision: indoor estimate,
   ranked fixes, travel-mode ranking, mask level, timing. Same input, same output.
2. **GenAI layer (Gemini, coming next)** turns the user's free-text plan into structured data,
   asks one follow-up when the plan is vague, and explains the rule engine's results in friendly
   language (including Hindi). It explains the numbers; it never invents them.

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
All tunable numbers (infiltration, source strengths, mode speeds, CO2 per km, mask effect) live in
`app/assumptions.py` and are rough, illustrative estimates, not measurements. PM2.5 is converted to
the Indian NAQI using CPCB bands, applied to the reading we have (CPCB uses 24-hour averages).

## Security and efficiency
- Strict input validation everywhere; request size cap, JSON-only bodies, per-client rate limit.
- Gemini key is read from the environment (never committed) and sent in a header, never in a URL.
- User text is length-capped, cleaned, wrapped as data, and Gemini's JSON is re-validated before use.
- Security headers (CSP, nosniff, no-referrer) and no stack traces in responses.
- Live AQI and geocoding are cached with a TTL and a size cap, so repeat requests cost nothing.
- If Gemini is down, rule-based template text is used and the app keeps working.

## API
- `GET /api/health`
- `POST /api/assess` with `{home, location: {city} or {latitude, longitude}, language}`
- `POST /api/plan` with `{home, location, timing: "fixed"|"flexible", plan_text}` or a structured `plan`

## Configuration
Set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`) as environment variables or Codespaces secrets.
Without a key the app runs in template mode. Air data comes from Open-Meteo (no key needed).

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
  server.py       Flask API with limits and security headers
  cache.py, ratelimit.py, config.py
tests/            pytest suite (no test touches the network)
```

## Run
```
pip install -r requirements.txt
pytest                      # run the tests
python -m app.server        # start the API on port 5000
```
