// Builds <name>-blink.webp: a mascot's directions sheet with each cell's eyes closed, so a blink keeps the head
// where it looks. Image processing only (no model): find the two solid dark eye blobs per cell, paint the fur over
// them by harmonic fill from the fur around, then draw a closed lid. Writes a .png beside each .webp for review.
// It does not judge the result: check every cell by eye and list the good directions in BLINK_DIRECTIONS (Mascot.tsx).
// Usage, from ui-be/web (needs @playwright/test and a local Chrome):
//   node scripts/make-mascot-blink.mjs src/assets/mascots <outDir> fox owl ...
import { readFileSync, writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";

const [assets, out, ...names] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage();
await page.setContent("<html><body></body></html>");

const report = {};
for (const name of names) {
  const src = `data:image/webp;base64,${readFileSync(`${assets}/${name}-directions.webp`).toString("base64")}`;
  const result = await page.evaluate(async (src) => {
    const img = new Image();
    img.src = src;
    await img.decode();
    const W = img.width, H = img.height, C = W / 3;
    const canvas = document.createElement("canvas");
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, W, H).data;
    const lum = (i) => 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    // Fur, not an eye's grey rim or white highlight: light, and tinted (cream and orange are never neutral grey).
    const isFur = (i) => lum(i) > 120 && Math.max(data[i], data[i + 1], data[i + 2]) - Math.min(data[i], data[i + 1], data[i + 2]) > 22;
    const cells = [];
    const lids = [];

    for (let cell = 0; cell < 9; cell++) {
      const x0 = (cell % 3) * C, y0 = Math.floor(cell / 3) * C;
      const n = Math.round(C);
      // Dark, opaque pixels: pupils, outlines, ear tips, nose.
      const dark = new Uint8Array(n * n);
      for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
        const i = ((y0 + y) * W + (x0 + x)) * 4;
        dark[y * n + x] = data[i + 3] > 200 && lum(i) < 75 ? 1 : 0;
      }
      // Close the white highlights inside a pupil first, so the eye is one solid blob.
      const morph = (src, r, keep) => {
        const res = new Uint8Array(n * n);
        for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
          let all = true, any = false;
          for (let dy = -r; dy <= r && (all || !any); dy++) for (let dx = -r; dx <= r; dx++) {
            if (dx * dx + dy * dy > r * r) continue;
            const yy = y + dy, xx = x + dx;
            const v = yy >= 0 && yy < n && xx >= 0 && xx < n ? src[yy * n + xx] : 0;
            if (v) any = true; else all = false;
          }
          res[y * n + x] = keep === "erode" ? (all ? 1 : 0) : (any ? 1 : 0);
        }
        return res;
      };
      const r = Math.max(2, Math.round(n * 0.012));
      const closed = morph(morph(dark, r, "dilate"), r, "erode");
      // Opening drops thin strokes (outlines, mouth, whiskers) and keeps solid blobs.
      const open = morph(morph(closed, Math.round(n * 0.018), "erode"), Math.round(n * 0.018), "dilate");
      // Connected components of the solid blobs.
      const label = new Int32Array(n * n);
      const blobs = [];
      for (let start = 0; start < n * n; start++) {
        if (!open[start] || label[start]) continue;
        const id = blobs.length + 1;
        const stack = [start];
        label[start] = id;
        let minX = n, minY = n, maxX = 0, maxY = 0, area = 0;
        while (stack.length) {
          const p = stack.pop();
          const x = p % n, y = (p - x) / n;
          area++;
          if (x < minX) minX = x; if (x > maxX) maxX = x; if (y < minY) minY = y; if (y > maxY) maxY = y;
          for (const q of [p - 1, p + 1, p - n, p + n]) {
            if (q < 0 || q >= n * n || label[q] || !open[q]) continue;
            if (Math.abs((q % n) - x) > 1) continue;
            label[q] = id;
            stack.push(q);
          }
        }
        blobs.push({ id, minX, minY, maxX, maxY, area });
      }
      // Eyes: sizeable, roundish, solid blobs in the face band (not the ear tips at the top, not the tiny nose).
      const eyes = blobs
        .map((b) => ({ ...b, w: b.maxX - b.minX + 1, h: b.maxY - b.minY + 1 }))
        .filter((b) => {
          const fill = b.area / (b.w * b.h);
          const aspect = b.w / b.h;
          const cy = (b.minY + b.maxY) / 2 / n;
          return b.h > n * 0.06 && b.h < n * 0.25 && b.w > n * 0.03 && fill > 0.55 && aspect > 0.35 && aspect < 1.4 && cy > 0.22 && cy < 0.72;
        })
        .sort((a, b) => b.area - a.area)
        .slice(0, 2);
      cells.push({ cell, eyes: eyes.map(({ minX, minY, w, h, area }) => ({ x: minX, y: minY, w, h, area })) });

      for (const eye of eyes) lids.push({ x0, y0, eye });
    }

    // Distance (in px, capped) from each pixel to the nearest see-through one: the face's outer outline lies close to it.
    const CAP = Math.round(C * 0.03);
    const edge = new Uint8Array(W * H).fill(CAP);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (data[(y * W + x) * 4 + 3] < 200) edge[y * W + x] = 0;
    for (let pass = 0; pass < CAP; pass++) {
      for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
        const p = y * W + x;
        const m = Math.min(edge[p - 1], edge[p + 1], edge[p - W], edge[p + W]) + 1;
        if (m < edge[p]) edge[p] = m;
      }
    }

    const outImage = ctx.getImageData(0, 0, W, H);
    const px = outImage.data;
    const strokes = [];
    for (const { x0, y0, eye } of lids) {
      const cx = x0 + eye.minX + eye.w / 2, cy = y0 + eye.minY + eye.h / 2;
      const rx = eye.w / 2, ry = eye.h / 2;
      // The fur colour around the eye: median of the light, opaque pixels in a ring just outside it.
      const ring = [];
      for (let y = Math.floor(cy - ry * 2); y <= cy + ry * 2; y++) for (let x = Math.floor(cx - rx * 2); x <= cx + rx * 2; x++) {
        const d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2;
        if (d < 2.2 || d > 3.6 || x < x0 || x >= x0 + C || y < y0 || y >= y0 + C) continue;
        const i = (y * W + x) * 4;
        if (data[i + 3] > 230 && isFur(i)) ring.push([data[i], data[i + 1], data[i + 2]]);
      }
      if (ring.length < 20) continue;
      const median = (k) => ring.map((p) => p[k]).sort((a, b) => a - b)[Math.floor(ring.length / 2)];
      const fur = [median(0), median(1), median(2)];
      // Cover the whole eye (pupil, rim, highlights) but never the face's outer outline or the background.
      const ax = rx * 1.45 + 3, ay = ry * 1.36 + 3;
      const left = Math.max(x0, Math.floor(cx - ax * 1.6)), right = Math.min(x0 + C - 1, Math.ceil(cx + ax * 1.6));
      const top = Math.max(y0, Math.floor(cy - ay * 1.6)), bottom = Math.min(y0 + C - 1, Math.ceil(cy + ay * 1.6));
      const bw = right - left + 1, bh = bottom - top + 1;
      // 2 = to fill, 1 = known fur, 0 = ignored (outline, background).
      const kind = new Uint8Array(bw * bh);
      const coverage = new Float32Array(bw * bh);
      const value = new Float32Array(bw * bh * 3);
      for (let y = top; y <= bottom; y++) for (let x = left; x <= right; x++) {
        const q = (y - top) * bw + (x - left), p = y * W + x, i = p * 4;
        const d = Math.sqrt(((x - cx) / ax) ** 2 + ((y - cy) / ay) ** 2);
        const opaque = data[i + 3] >= 240;
        if (d <= 1.12 && opaque) {
          const nearEdge = edge[p] < CAP;
          const a = (d <= 1 ? 1 : 1 - (d - 1) / 0.12) * (nearEdge ? Math.max(0, (edge[p] - CAP * 0.45) / (CAP * 0.55)) : 1);
          if (a > 0) {
            kind[q] = 2;
            coverage[q] = a;
            for (let k = 0; k < 3; k++) value[q * 3 + k] = fur[k];
            continue;
          }
        }
        if (d > 1.12 && opaque && isFur(i)) {
          kind[q] = 1;
          for (let k = 0; k < 3; k++) value[q * 3 + k] = data[i + k];
        }
      }
      // Harmonic fill: each pixel to fill becomes the mean of its usable neighbours until the colours settle, so the
      // fur around the eye (including a cream/orange boundary through it) flows smoothly across the closed lid.
      for (let iter = 0; iter < 400; iter++) {
        for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
          const q = y * bw + x;
          if (kind[q] !== 2) continue;
          let r = 0, g = 0, b = 0, count = 0;
          for (const n of [q - 1, q + 1, q - bw, q + bw]) {
            if (n < 0 || n >= bw * bh || !kind[n]) continue;
            if ((n === q - 1 && x === 0) || (n === q + 1 && x === bw - 1)) continue;
            r += value[n * 3]; g += value[n * 3 + 1]; b += value[n * 3 + 2]; count++;
          }
          if (!count) continue;
          value[q * 3] = r / count; value[q * 3 + 1] = g / count; value[q * 3 + 2] = b / count;
        }
      }
      for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
        const q = y * bw + x;
        if (kind[q] !== 2) continue;
        const i = ((top + y) * W + (left + x)) * 4, a = coverage[q];
        for (let k = 0; k < 3; k++) px[i + k] = Math.round(px[i + k] * (1 - a) + value[q * 3 + k] * a);
      }
      strokes.push({ cx, cy, rx, ry, w: eye.w, h: eye.h });
    }
    ctx.putImageData(outImage, 0, 0);
    // The closed lid: a soft downward curve across where the eye was, with rounded ends.
    for (const { cx, cy, rx, ry, h } of strokes) {
      ctx.save();
      ctx.strokeStyle = "rgb(52,30,22)";
      ctx.lineCap = "round";
      ctx.lineWidth = Math.max(3, h * 0.11);
      ctx.beginPath();
      const half = Math.max(rx * 1.05, ry * 0.55);
      const yLine = cy + ry * 0.15;
      ctx.moveTo(cx - half, yLine - ry * 0.05);
      ctx.quadraticCurveTo(cx, yLine + ry * 0.45, cx + half, yLine - ry * 0.05);
      ctx.stroke();
      ctx.restore();
    }
    return { cells, webp: canvas.toDataURL("image/webp", 0.92), png: canvas.toDataURL("image/png") };
  }, src);
  writeFileSync(`${out}/${name}-blink.webp`, Buffer.from(result.webp.split(",")[1], "base64"));
  writeFileSync(`${out}/${name}-blink.png`, Buffer.from(result.png.split(",")[1], "base64"));
  report[name] = result.cells.map((c) => c.eyes.length);
}
console.log(JSON.stringify(report));
await browser.close();
