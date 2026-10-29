export const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value))

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t

export const scale = (value: number, min: number, max: number, outMin: number, outMax: number): number => {
  if (max === min) return outMin
  return outMin + ((value - min) / (max - min)) * (outMax - outMin)
}
