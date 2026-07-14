/**
 * Sync script: copies public files from workspace to desktop deploy folder.
 * Run with: node sync-to-deploy.js
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, 'public');
const DEST = 'C:\\Users\\Administrator\\Desktop\\veimia-ugc-hub\\public';

function copyRecursive(src, dest) {
  if (!fs.existsSync(dest)) {
    fs.mkdirSync(dest, { recursive: true });
  }

  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      copyRecursive(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

copyRecursive(SRC, DEST);

// Also copy vercel.json if it exists
const vercelSrc = path.join(__dirname, 'vercel.json');
const vercelDest = 'C:\\Users\\Administrator\\Desktop\\veimia-ugc-hub\\vercel.json';
if (fs.existsSync(vercelSrc)) {
  fs.copyFileSync(vercelSrc, vercelDest);
}

console.log('✅ Synced workspace → deploy folder');
console.log('   From: ' + SRC);
console.log('   To:   ' + DEST);
