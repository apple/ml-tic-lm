/*
For licensing see accompanying LICENSE file.
Copyright (C) 2025 Apple Inc. All Rights Reserved.

*/

var { Readability } = require('@mozilla/readability');
var { JSDOM } = require('jsdom');
//const fs = require('fs');
const fs = require('node:fs/promises');


async function readFile(filePath) {
  try {
    const content = await fs.readFile(filePath, 'utf8');
    return content;

  } catch (err) {
    console.error('Error reading file:', err);
    return null;
  }
}

function extractText(article) {
  if (!article || typeof article !== 'object') {
    throw new Error('Invalid Readability object');
  }

  const { title, textContent } = article;
  
  if (typeof title !== 'string' || typeof textContent !== 'string') {
    throw new Error('Title or textContent is not a string');
  }

  return `${title}\n\n${textContent}`;
}

function clean(text) {
  // Replace two or more newlines with a single newline
  let c = text.replace(/\n{3,}/g, '\n');
  c = c.replace("¶","");
  return c;
}

async function main() {
    const inp = process.argv[2];
    const out = `${inp}.txt`;
    const html = await readFile(inp);
    var doc = new JSDOM(html);
    let reader = new Readability(doc.window.document);
    let article = reader.parse();
    //console.log(article);
    const extracted = extractText(article);
    const cleaned = clean(extracted);
    await fs.writeFile(out, cleaned);
    // console.log(clean(extracted));
}

main()
