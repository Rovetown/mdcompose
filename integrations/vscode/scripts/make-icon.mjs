// Renders media/icon-source.svg to media/icon.png, the extension's listing icon.
//
//   node scripts/make-icon.mjs
//
// The marketplaces accept only a raster image for the listing icon (the packaging
// tool rejects an SVG), so the PNG is committed and this script is only needed to
// regenerate it. The size is 256 pixels square, above the 128 pixel minimum, with
// a transparent background.
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Resvg } from "@resvg/resvg-js";

const here = path.dirname(fileURLToPath(import.meta.url));
const media = path.resolve(here, "..", "media");
const svg = readFileSync(path.join(media, "icon-source.svg"), "utf8");
const png = new Resvg(svg, { fitTo: { mode: "width", value: 256 } }).render().asPng();
writeFileSync(path.join(media, "icon.png"), png);
console.log(`Wrote media/icon.png (${png.length} bytes)`);
