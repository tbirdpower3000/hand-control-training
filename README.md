# Hand control training (v0.14)

A one-minute training page for the webcam hand control in the [Planetary Modeling Atlas](https://tbirdpower3000.github.io/planetary-atlas-v15mk2/). It teaches the atlas how *your* hand moves, so the cursor reaches the whole screen, your pinch is read reliably, and buttons are as easy to hit as you need.

**Use it:** https://tbirdpower3000.github.io/hand-control-training/ (Chrome, Edge or Safari, with a webcam).

## What it does

1. Asks which hand you use, how steady it is, how far you sit from the camera, and which cursor and sounds you want.
2. **Reach:** you move your open hand to four comfortable corners, and the page maps that area to the whole screen.
3. **Pinch:** open hand, then a firm pinch, three times, to set your own pinch threshold.
4. **Hold still:** three seconds on a dot, to measure how much the cursor wobbles and set the smoothing.
5. **Targets:** eight buttons to pinch, to measure overshoots, misses and time, which set how strongly buttons pull the cursor in.
6. After each step it asks one question: overall, how easy was that, from 1 (very hard, a lot of effort) to 7 (easy, no effort). You pinch a number and confirm it, or let it carry on by itself from what it measured.

The profile (a few numbers) is saved in your browser. The atlas, which lives on the same site, picks it up the next time you start hand control, and its 🎯 Adaptive aim keeps fine-tuning it as you go. You can also download the profile as a file and open it in the atlas with "Open a planet pack".

## Sharing results

At the end you can **share your results with the project**. It opens a GitHub issue pre-filled with the numbers (settings, measurements, your answers and ratings, browser type, screen size), and you press Submit yourself. A bot checks the numbers, stores them in `data/results.jsonl`, recomputes `data/defaults.json` (the medians, overall and per steadiness answer), and closes the issue. The atlas loads those shared defaults as its starting settings; a personal profile always overrides them.

Please read [PRIVACY.md](PRIVACY.md) first. In short: the camera never leaves your computer; sharing is optional, public, and under your GitHub account; this is not a medical test.

## Files

- `index.html`: the training page. No build step; everything is in this one file. Hand tracking is Google's MediaPipe Hand Landmarker (loaded from jsDelivr; the model from storage.googleapis.com), run entirely in your browser.
- `scripts/collect.py`, `.github/workflows/collect.yml`: the collector bot.
- `data/results.jsonl`, `data/defaults.json`: shared results and the defaults built from them.

## Credits and licence

Built with Claude by tbirdpower3000 and contributors, for the Planetary Modeling Atlas. Hand tracking: [MediaPipe](https://ai.google.dev/edge/mediapipe) (Apache-2.0). Fonts: Instrument Sans and JetBrains Mono via Google Fonts. The sounds are made in the page with the Web Audio API. The code in this repository is released under the Apache-2.0 licence (see LICENSE).
