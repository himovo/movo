export type ModelTestKind = 'chat' | 'embedding' | 'rerank' | 'image';

export function resolveModelTestKind(capabilities: readonly string[]): ModelTestKind {
  const values = new Set(capabilities.map((item) => String(item || '').trim().toLowerCase()));
  if (values.has('image_generation') || values.has('image')) return 'image';
  if (values.has('chat') || values.has('text') || values.has('vision')) return 'chat';
  if (values.has('embedding')) return 'embedding';
  if (values.has('rerank')) return 'rerank';
  return 'chat';
}
