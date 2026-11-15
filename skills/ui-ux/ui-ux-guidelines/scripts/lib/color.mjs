const clamp01 = (value) => Math.min(1, Math.max(0, value));
const to8bit = (unit) => Math.round(clamp01(unit) * 255);

function parseAlpha(part) {
  if (part === undefined) return 1;
  return clamp01(part.endsWith("%") ? parseFloat(part) / 100 : parseFloat(part));
}

function parseHue(part) {
  const value = parseFloat(part);
  if (part.endsWith("rad")) return (value * 180) / Math.PI;
  if (part.endsWith("turn")) return value * 360;
  if (part.endsWith("grad")) return value * 0.9;
  return value;
}

function hslToRgb(hue, saturation, lightness) {
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const sector = (((hue % 360) + 360) % 360) / 60;
  const second = chroma * (1 - Math.abs((sector % 2) - 1));
  const base = [
    [chroma, second, 0],
    [second, chroma, 0],
    [0, chroma, second],
    [0, second, chroma],
    [second, 0, chroma],
    [chroma, 0, second],
  ][Math.floor(sector) % 6];
  const offset = lightness - chroma / 2;
  return base.map((channel) => to8bit(channel + offset));
}

const gammaEncode = (linear) =>
  linear <= 0.0031308 ? 12.92 * linear : 1.055 * Math.pow(linear, 1 / 2.4) - 0.055;
const gammaDecode = (encoded) =>
  encoded <= 0.04045 ? encoded / 12.92 : Math.pow((encoded + 0.055) / 1.055, 2.4);

function oklabToRgb(lightness, a, b) {
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ].map((linear) => to8bit(gammaEncode(clamp01(linear))));
}

export function oklchLightness({ r, g, b }) {
  const [lr, lg, lb] = [r, g, b].map((channel) => gammaDecode(channel / 255));
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  return Math.round((0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s) * 1000) / 1000;
}

function parseHex(text) {
  const digits = text.slice(1);
  if (!/^([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(digits)) return null;
  const full = digits.length <= 4 ? [...digits].map((d) => d + d).join("") : digits;
  const channel = (index) => parseInt(full.slice(index * 2, index * 2 + 2), 16);
  return { r: channel(0), g: channel(1), b: channel(2), a: full.length === 8 ? channel(3) / 255 : 1 };
}

const percentOrNumber = (part, percentScale) =>
  part.endsWith("%") ? (parseFloat(part) / 100) * percentScale : parseFloat(part);

function parseFunctional(name, parts) {
  const [first, second, third, alpha] = parts;
  if (name === "rgb" || name === "rgba") {
    const [r, g, b] = [first, second, third].map((t) =>
      Math.round(Math.min(255, Math.max(0, percentOrNumber(t, 255)))),
    );
    return { r, g, b, a: parseAlpha(alpha) };
  }
  if (name === "hsl" || name === "hsla") {
    const [r, g, b] = hslToRgb(parseHue(first), clamp01(parseFloat(second) / 100), clamp01(parseFloat(third) / 100));
    return { r, g, b, a: parseAlpha(alpha) };
  }
  if (name === "oklch") {
    const chroma = percentOrNumber(second, 0.4);
    const hue = (parseHue(third) * Math.PI) / 180;
    const [r, g, b] = oklabToRgb(percentOrNumber(first, 1), chroma * Math.cos(hue), chroma * Math.sin(hue));
    return { r, g, b, a: parseAlpha(alpha) };
  }
  if (name === "oklab") {
    const [r, g, b] = oklabToRgb(percentOrNumber(first, 1), percentOrNumber(second, 0.4), percentOrNumber(third, 0.4));
    return { r, g, b, a: parseAlpha(alpha) };
  }
  return null;
}

export function parseColor(input) {
  const text = String(input).trim().toLowerCase();
  const named = { transparent: { r: 0, g: 0, b: 0, a: 0 }, black: { r: 0, g: 0, b: 0, a: 1 }, white: { r: 255, g: 255, b: 255, a: 1 } };
  let parsed = named[text] ?? null;
  if (!parsed && text.startsWith("#")) parsed = parseHex(text);
  const call = text.match(/^([a-z]+)\((.*)\)$/);
  if (!parsed && call) {
    const parts = call[2].replace(/[,/]/g, " ").trim().split(/\s+/);
    if (call[1] === "color" && parts[0] === "srgb") {
      const [r, g, b] = parts.slice(1, 4).map((t) => to8bit(percentOrNumber(t, 1)));
      parsed = { r, g, b, a: parseAlpha(parts[4]) };
    } else if (parts.length >= 3) {
      parsed = parseFunctional(call[1], parts.map((t) => (t === "none" ? "0" : t)));
    }
  }
  if (!parsed || [parsed.r, parsed.g, parsed.b, parsed.a].some(Number.isNaN)) {
    throw new Error(`unparsable color: ${input}`);
  }
  return parsed;
}

export function compositeOver(top, bottom, alpha = top.a) {
  const mix = (key) => Math.round(top[key] * alpha + bottom[key] * (1 - alpha));
  return { r: mix("r"), g: mix("g"), b: mix("b"), a: 1 };
}

export function toHex({ r, g, b }) {
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}

function relativeLuminance({ r, g, b }) {
  const [lr, lg, lb] = [r, g, b].map((channel) => gammaDecode(channel / 255));
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

export function wcagRatio(first, second) {
  const [lighter, darker] = [relativeLuminance(first), relativeLuminance(second)].sort((x, y) => y - x);
  return (lighter + 0.05) / (darker + 0.05);
}

function apcaLuminance({ r, g, b }) {
  const y =
    0.2126729 * Math.pow(r / 255, 2.4) + 0.7151522 * Math.pow(g / 255, 2.4) + 0.072175 * Math.pow(b / 255, 2.4);
  return y > 0.022 ? y : y + Math.pow(0.022 - y, 1.414);
}

export function apcaLc(text, background) {
  const textY = apcaLuminance(text);
  const backgroundY = apcaLuminance(background);
  if (Math.abs(backgroundY - textY) < 0.0005) return 0;
  if (backgroundY > textY) {
    const contrast = (Math.pow(backgroundY, 0.56) - Math.pow(textY, 0.57)) * 1.14;
    return contrast < 0.1 ? 0 : (contrast - 0.027) * 100;
  }
  const contrast = (Math.pow(backgroundY, 0.65) - Math.pow(textY, 0.62)) * 1.14;
  return contrast > -0.1 ? 0 : (contrast + 0.027) * 100;
}

function mixToward(color, pole, amount) {
  const mix = (key) => Math.round(color[key] + (pole[key] - color[key]) * amount);
  return { r: mix("r"), g: mix("g"), b: mix("b"), a: 1 };
}

function smallestPassingMix(color, pole, passes) {
  if (!passes(mixToward(color, pole, 1))) return null;
  let low = 0;
  let high = 1;
  while (high - low > 0.001) {
    const middle = (low + high) / 2;
    if (passes(mixToward(color, pole, middle))) high = middle;
    else low = middle;
  }
  return { amount: high, color: mixToward(color, pole, high) };
}

const BLACK = { r: 0, g: 0, b: 0, a: 1 };
const WHITE = { r: 255, g: 255, b: 255, a: 1 };

function nearestPassing(color, passes) {
  const darker = smallestPassingMix(color, BLACK, passes);
  const lighter = smallestPassingMix(color, WHITE, passes);
  if (darker && lighter) return lighter.amount < darker.amount ? lighter.color : darker.color;
  return (darker ?? lighter)?.color ?? null;
}

export function correctiveColor(foreground, background, pairPasses) {
  const fixedForeground = nearestPassing(foreground, (candidate) => pairPasses(candidate, background));
  if (fixedForeground) return { target: "foreground", color: fixedForeground };
  const fixedBackground = nearestPassing(background, (candidate) => pairPasses(foreground, candidate));
  if (fixedBackground) return { target: "background", color: fixedBackground };
  return null;
}

export function resolveBackground(layers) {
  const stack = [];
  for (const layer of layers) {
    if (layer.image) return { inconclusive: "background-image" };
    const color = parseColor(layer.color);
    if (color.a === 0) continue;
    stack.push(color);
    if (color.a === 1) break;
  }
  let resolved = stack.length && stack[stack.length - 1].a === 1 ? stack.pop() : WHITE;
  while (stack.length) resolved = compositeOver(stack.pop(), resolved);
  return { color: resolved };
}
