const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

async function convertHtmlToPng(htmlPath, outputPath) {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();

  // Set viewport to exact Instagram carousel size
  await page.setViewport({
    width: 1080,
    height: 1080,
    deviceScaleFactor: 2 // 2x for high quality (2160x2160 actual, scales to 1080x1080)
  });

  // Load HTML file
  const fileUrl = `file:///${htmlPath.replace(/\\/g, '/')}`;
  await page.goto(fileUrl, { waitUntil: 'networkidle0' });

  // Wait for fonts to load
  await page.evaluate(() => document.fonts.ready);
  await new Promise(resolve => setTimeout(resolve, 1000));

  // Take screenshot
  await page.screenshot({
    path: outputPath,
    type: 'png',
    clip: {
      x: 0,
      y: 0,
      width: 1080,
      height: 1080
    }
  });

  await browser.close();
  console.log(`Created: ${outputPath}`);
}

async function convertAllSlides(inputDir, outputDir) {
  // Ensure output directory exists
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  // Get all HTML files
  const htmlFiles = fs.readdirSync(inputDir)
    .filter(f => f.endsWith('.html'))
    .sort();

  console.log(`Found ${htmlFiles.length} HTML files to convert`);

  for (const htmlFile of htmlFiles) {
    const htmlPath = path.join(inputDir, htmlFile);
    const pngFile = htmlFile.replace('.html', '.png');
    const outputPath = path.join(outputDir, pngFile);

    try {
      await convertHtmlToPng(htmlPath, outputPath);
    } catch (err) {
      console.error(`Error converting ${htmlFile}:`, err.message);
    }
  }

  console.log('\nConversion complete!');
}

// Main execution
const inputDir = process.argv[2] || 'D:\\commerce\\marketing\\instagram\\란도린-디퓨저';
const outputDir = process.argv[3] || path.join(inputDir, 'png');

convertAllSlides(inputDir, outputDir);
