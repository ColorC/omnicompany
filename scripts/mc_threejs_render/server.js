'use strict';
/**
 * mc_threejs_render/server.js
 * Serves static files + proxies texture paths, then uses puppeteer-core to
 * render the Three.js scene and save a PNG.
 *
 * Usage:
 *   node server.js <texture_path> <output_png> [width] [height] [uvtype] [model_parts_json]
 *
 *   uvtype: guard (128x128) | steve (64x64) | wide (64x32) | dynamic   default: guard
 *   model_parts_json: path to model_{family}.json (required when uvtype=dynamic)
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const DIR = __dirname;
const PORT = 3791;

// ─── Simple static file server ─────────────────────────────────────────────
const MIME = {
  '.html': 'text/html',
  '.js':   'application/javascript',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
};

function startServer(texturePath, modelPartsPath) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const urlPath = decodeURIComponent(req.url.split('?')[0]);

      // Special route: /texture.png → serve the actual texture file
      if (urlPath === '/texture.png') {
        fs.readFile(texturePath, (err, data) => {
          if (err) { res.writeHead(404); res.end('texture not found'); return; }
          res.writeHead(200, { 'Content-Type': 'image/png' });
          res.end(data);
        });
        return;
      }

      // Special route: /modelparts.json → serve the dynamic model parts file
      if (urlPath === '/modelparts.json') {
        if (!modelPartsPath) { res.writeHead(404); res.end('no model parts configured'); return; }
        fs.readFile(modelPartsPath, (err, data) => {
          if (err) { res.writeHead(404); res.end('model parts not found'); return; }
          res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
          res.end(data);
        });
        return;
      }

      // Serve files under DIR (handles /render.html, /three/... etc)
      const filePath = path.join(DIR, urlPath);
      fs.readFile(filePath, (err, data) => {
        if (err) { res.writeHead(404); res.end('not found: ' + urlPath); return; }
        const ext = path.extname(filePath);
        res.writeHead(200, {
          'Content-Type': MIME[ext] || 'application/octet-stream',
          'Access-Control-Allow-Origin': '*',
        });
        res.end(data);
      });
    });

    server.listen(PORT, '127.0.0.1', () => resolve(server));
  });
}

// ─── Main ───────────────────────────────────────────────────────────────────
async function main() {
  const [,, texturePath, outputPath, wStr, hStr, uvtype, modelPartsPath] = process.argv;
  if (!texturePath || !outputPath) {
    console.error('Usage: node server.js <texture_path> <output_png> [width] [height] [uvtype] [model_parts_json]');
    console.error('  uvtype: guard|steve|wide|dynamic   default: guard');
    process.exit(1);
  }

  const W = parseInt(wStr || '320');
  const H = parseInt(hStr || '480');
  const UV = uvtype || 'guard';

  const server = await startServer(texturePath, modelPartsPath || null);
  console.log(`[server] listening on http://127.0.0.1:${PORT}`);

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--hide-scrollbars'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: W, height: H });

    const mpParam = (UV === 'dynamic' && modelPartsPath) ? `&modelparts=http://127.0.0.1:${PORT}/modelparts.json` : '';
    const url = `http://127.0.0.1:${PORT}/render.html?w=${W}&h=${H}&uvtype=${UV}${mpParam}`;
    console.log(`[browser] opening ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded' });

    // Wait for Three.js render to complete (texture load + render)
    await page.waitForFunction(() => window.__renderDone === true, { timeout: 20000, polling: 200 });

    // Screenshot the canvas element (not the full page)
    const canvas = await page.$('canvas');
    if (canvas) {
      await canvas.screenshot({ path: outputPath });
    } else {
      await page.screenshot({ path: outputPath });
    }

    console.log(`[done] saved ${outputPath}`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
