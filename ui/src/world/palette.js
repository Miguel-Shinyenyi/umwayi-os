// The nightwatch palette. Dark, low brightness. Red, mint and amber carry a meaning only at Rules (the three answers),
// the Kill switch (red when on) and the Logbook (a broken chain). Everywhere else they are light.
export const TOKENS = {
  base: 0x0e1310,
  ink: 0xeee8db,
  amber: 0xe0a965,
  mint: 0x9cc39a,
  red: 0xe07a6f,
};
export const SCENE = {
  stone: 0x59635d,
  stoneDark: 0x38413c,
  wood: 0x6a513a,
  woodDark: 0x43332a,
  thatch: 0x75623f,
  roof: 0x53443a,
  wool: 0xc4bba7,
  skin: 0x2a2926,
  lawn: 0x30463a,
  grass: 0x2a3f32,
  parchment: 0xb3a47f,
  line: 0xa8a393,
  metal: 0x2d322f,
  water: 0x3c6b73,
  rim: 0x8d8b7c,
};
// Calm mode keeps the same hues at lower strength.
export const CALM = { glow: 0.5, bloom: 0.5, exposure: 0.84, contour: 0, fogBoost: 1.12 };
export const NORMAL = { glow: 1, bloom: 1, exposure: 1, contour: 1, fogBoost: 1 };
