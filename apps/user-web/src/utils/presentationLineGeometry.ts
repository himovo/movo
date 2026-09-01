export type AffineMatrix = [number, number, number, number, number, number]

export interface Point { x: number; y: number }

export function transformPoint(point: Point, matrix: AffineMatrix): Point {
  const [a, b, c, d, e, f] = matrix
  return {
    x: a * point.x + c * point.y + e,
    y: b * point.x + d * point.y + f,
  }
}

export function linePageEndpoints(line: any): { start: Point; end: Point } {
  const points = typeof line.calcLinePoints === 'function'
    ? line.calcLinePoints()
    : { x1: line.x1 || 0, y1: line.y1 || 0, x2: line.x2 || 0, y2: line.y2 || 0 }
  const matrix = line.calcTransformMatrix() as AffineMatrix
  return {
    start: transformPoint({ x: points.x1, y: points.y1 }, matrix),
    end: transformPoint({ x: points.x2, y: points.y2 }, matrix),
  }
}
