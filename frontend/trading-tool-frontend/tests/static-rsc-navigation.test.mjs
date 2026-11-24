import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { request } from 'node:http';
import test from 'node:test';

const require = createRequire(import.meta.url);
const { server } = require('../server.js');

function rawRequest(port, pathname) {
  return new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path: pathname }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject);
    req.end();
  });
}

test('browser navigation to an RSC text file returns to the HTML route', async () => {
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  try {
    const document = await fetch(`${origin}/portfolio.txt?_rsc=stale&view=paper`, {
      redirect: 'manual',
      headers: { Accept: 'text/html', 'Sec-Fetch-Dest': 'document' },
    });
    assert.equal(document.status, 302);
    assert.equal(document.headers.get('location'), '/portfolio?view=paper');
    assert.match(document.headers.get('cache-control'), /no-store/);

    const head = await fetch(`${origin}/portfolio.txt`, {
      method: 'HEAD', redirect: 'manual',
      headers: { Accept: 'text/html', 'Sec-Fetch-Dest': 'document' },
    });
    assert.equal(head.status, 302);
    assert.equal(head.headers.get('location'), '/portfolio');

    const ordinaryText = await fetch(`${origin}/missing.txt`, {
      redirect: 'manual',
      headers: { Accept: 'text/html', 'Sec-Fetch-Dest': 'document' },
    });
    assert.equal(ordinaryText.status, 404);

    const rsc = await fetch(`${origin}/portfolio.txt?_rsc=current`, {
      headers: { Accept: 'text/x-component', 'Sec-Fetch-Dest': 'empty' },
    });
    assert.equal(rsc.status, 200);
    assert.match(await rsc.text(), /\$Sreact\.fragment/);

    const html = await fetch(`${origin}/portfolio`);
    assert.equal(html.status, 200);
    assert.match(html.headers.get('content-type'), /text\/html/);

    for (const pathname of ['/../server.js', '/%2e%2e/server.js', '/%2e%2e%2fserver.js']) {
      const traversal = await rawRequest(server.address().port, pathname);
      assert.equal(traversal.status, 400);
      assert.doesNotMatch(traversal.body, /const PORT/);
    }
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});
