// Usage: HYBRID_PLAYWRIGHT_PATH=/path/to/playwright node scripts/smoke_web.cjs
const {chromium} = require(process.env.HYBRID_PLAYWRIGHT_PATH || 'playwright');
const fs = require('fs');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    const errors=[];page.on('pageerror', error=>errors.push(error.message));
    const {url}=JSON.parse(fs.readFileSync('/tmp/hybrid-web-fixture.json','utf8'));
    await page.goto(url);
    await page.waitForFunction(()=>document.getElementById('model').options.length===2);
    await page.selectOption('#model','qwen:fixture');
    await page.waitForFunction(()=>document.getElementById('skill').options.length===9);
    await page.fill('#skill-filter','debug');
    await page.selectOption('#skill','debug');
    await page.waitForFunction(()=>document.getElementById('skill-content').textContent.includes('hipótese'));
    await page.fill('#skill-filter','');
    await page.fill('#session','browser-test');
    await page.fill('#prompt','Explique o projeto');
    await page.click('#send');
    await page.waitForFunction(()=>document.getElementById('status').textContent==='Concluído');
    assert.match(await page.locator('#messages').innerText(), /<script>texto seguro<\/script>/);
    assert.match(await page.locator('#metrics').innerText(), /12 tokens/);
    assert.match(await page.locator('#metrics').innerText(), /Skill: debug/);
    await page.click('#load');
    await page.waitForFunction(()=>document.getElementById('status').textContent==='Sessão carregada');
    assert.equal(await page.locator('#messages article').count(),2);
    await page.getByText('Buscar no código',{exact:true}).click();
    await page.fill('#query','needle');await page.click('#search');
    await page.waitForFunction(()=>document.getElementById('search-results').textContent.includes('example.py'));
    await page.getByText('Aplicar uma correção',{exact:true}).click();
    await page.fill('#patch','--- a/example.py\n+++ b/example.py\n@@ -1,2 +1,2 @@\n def needle():\n-    return 1\n+    return 2\n');
    await page.click('#preview');await page.waitForFunction(()=>!document.getElementById('apply').disabled);
    await page.click('#apply');await page.waitForFunction(()=>document.getElementById('patch-result').textContent.includes('Arquivos alterados:'));
    await page.fill('#prompt','slow');await page.click('#send');
    await page.waitForFunction(()=>document.querySelector('#messages article:last-child pre').textContent.includes('aguarde'));
    await page.click('#cancel');await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Cancelado'));
    await page.screenshot({path:'reports/web-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
    await page.screenshot({path:'reports/web-mobile.png',fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('PASS: models, streaming, session, search, patch apply, cancellation, safe rendering, mobile width, skills');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
