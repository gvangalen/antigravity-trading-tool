const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 5002;
const PUBLIC_DIR = path.join(__dirname, 'out');

const mimeTypes = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.wav': 'audio/wav',
  '.mp4': 'video/mp4',
  '.woff': 'application/font-woff',
  '.ttf': 'application/font-ttf',
  '.eot': 'application/vnd.ms-fontobject',
  '.otf': 'application/font-otf',
  '.wasm': 'application/wasm',
  '.txt': 'text/plain'
};

function getCacheHeaders(filePath, statusCode = 200) {
  if (statusCode !== 200) {
    return {
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      Pragma: 'no-cache',
      Expires: '0'
    };
  }

  const relativePath = path.relative(PUBLIC_DIR, filePath).split(path.sep).join('/');
  const extension = path.extname(filePath).toLowerCase();

  if (relativePath.startsWith('_next/static/')) {
    return { 'Cache-Control': 'public, max-age=31536000, immutable' };
  }

  if (extension === '.html' || extension === '.txt' || extension === '.json') {
    return {
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      Pragma: 'no-cache',
      Expires: '0'
    };
  }

  return { 'Cache-Control': 'public, max-age=3600' };
}

function rscDocumentRedirect(req, filePath) {
  if (!['GET', 'HEAD'].includes(req.method) || path.extname(filePath) !== '.txt' ||
      !fs.existsSync(`${filePath.slice(0, -4)}.html`)) return null;

  const destination = req.headers['sec-fetch-dest'];
  const acceptsHtml = String(req.headers.accept || '').includes('text/html');
  if (destination !== 'document' && !(destination !== 'empty' && acceptsHtml)) return null;

  try {
    const url = new URL(req.url, 'http://localhost');
    url.pathname = url.pathname.slice(0, -4);
    url.searchParams.delete('_rsc');
    return `${url.pathname}${url.search}`;
  } catch {
    return null;
  }
}

const server = http.createServer((req, res) => {
  // Strip query string from URL to correctly find static files (e.g. macro.txt?_rsc=...)
  let cleanUrl;
  try {
    cleanUrl = decodeURIComponent(req.url.split('?')[0]);
  } catch {
    res.writeHead(400, getCacheHeaders(PUBLIC_DIR, 400));
    res.end('Bad Request');
    return;
  }
  const relativePath = cleanUrl === '/' ? 'index.html' : cleanUrl.replace(/^\/+/, '');
  let filePath = path.resolve(PUBLIC_DIR, relativePath);
  if (cleanUrl.includes('\0') || cleanUrl.includes('\\') ||
      cleanUrl.split('/').includes('..') ||
      !filePath.startsWith(`${PUBLIC_DIR}${path.sep}`)) {
    res.writeHead(400, getCacheHeaders(PUBLIC_DIR, 400));
    res.end('Bad Request');
    return;
  }

  const documentRedirect = rscDocumentRedirect(req, filePath);
  if (documentRedirect) {
    res.writeHead(302, {
      Location: documentRedirect,
      ...getCacheHeaders(filePath, 302)
    });
    res.end();
    return;
  }

  if (fs.existsSync(filePath)) {
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      const nestedIndex = path.join(filePath, 'index.html');
      const flatHtml = `${filePath}.html`;
      if (fs.existsSync(nestedIndex)) {
        filePath = nestedIndex;
      } else if (fs.existsSync(flatHtml)) {
        filePath = flatHtml;
      }
    }
  } else if (!path.extname(filePath)) {
    // Handige fallback voor Next.js static export (zonder .html in URL)
    filePath += '.html';
  }

  const extname = String(path.extname(filePath)).toLowerCase();
  const contentType = mimeTypes[extname] || 'application/octet-stream';

  fs.readFile(filePath, (error, content) => {
    if (error) {
      if (error.code === 'ENOENT') {
        fs.readFile(path.join(PUBLIC_DIR, '404.html'), (err, content404) => {
          res.writeHead(404, {
            'Content-Type': 'text/html',
            ...getCacheHeaders(filePath, 404)
          });
          res.end(content404 || '404 Not Found', 'utf-8');
        });
      } else {
        res.writeHead(500);
        res.end(`Sorry, check with the site admin for error: ${error.code} ..\n`);
      }
    } else {
      res.writeHead(200, {
        'Content-Type': contentType,
        ...getCacheHeaders(filePath)
      });
      res.end(content, 'utf-8');
    }
  });
});

if (require.main === module) {
  server.listen(PORT, () => {
    console.log(`🚀 Production server running at http://localhost:${PORT}/`);
  });
}

module.exports = { server };
