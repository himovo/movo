import { retryKnowledgeDocumentIndex, retryKnowledgeDocumentParse, type KnowledgeDocumentItem } from '@/api/knowledge-documents';

export function knowledgeDocumentRetryStage(document: KnowledgeDocumentItem): 'parse' | 'index' | null {
  if (document.parseStatus === 'failed' || document.chunkStatus === 'failed') return 'parse';
  if (document.indexStatus === 'failed' && document.chunkStatus === 'succeeded' && (document.ragChunkCount || document.chunkCount) > 0) return 'index';
  return null;
}

export function retryKnowledgeDocument(document: KnowledgeDocumentItem): Promise<KnowledgeDocumentItem> {
  const stage = knowledgeDocumentRetryStage(document);
  if (stage === 'index') return retryKnowledgeDocumentIndex(document.id);
  if (stage === 'parse') return retryKnowledgeDocumentParse(document.id);
  return Promise.reject(new Error('Document has no retryable failed stage'));
}
