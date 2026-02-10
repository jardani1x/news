# Daily News (Apple-style minimalist)

A clean, minimalist daily news site built with **jQuery** and deployed to **GitHub Pages**.

## Topics
- World
- Finance
- Technology
- Local Singapore

News data is generated into `data/news.json` by `build_news.py`, then rendered client-side by `script.js`.

## Local run
```bash
python3 build_news.py
python3 -m http.server 8080
# open http://localhost:8080
```

## Refresh news (runbook)
1. Regenerate static data:
   ```bash
   python3 build_news.py
   ```
2. Commit and push:
   ```bash
   git add data/news.json
   git commit -m "chore: refresh news data"
   git push
   ```
3. GitHub Pages will auto-update in ~1-2 minutes.

## Deploy notes
- Pages source: `main` branch, root folder.
- Live URL: `https://jardani1x.github.io/news/`
