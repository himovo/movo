import { apiClient } from './client';

export interface KnowledgeParseSettings {
  minChunkSize: number;
  maxChunkSize: number;
  chunkOverlap: number;
  updatedAt: string;
}

export interface KnowledgeParseSettingsPayload {
  minChunkSize: number;
  maxChunkSize: number;
  chunkOverlap: number;
}

export interface KnowledgeSettings {
  parse: KnowledgeParseSettingsPayload;
  embedding: {
    provider: 'model_center';
    modelInstanceId: string;
    dimension: number;
    batchSize: number;
    timeoutSeconds: number;
  };
  vectorStore: {
    type: 'weaviate' | 'qdrant' | 'milvus' | 'elasticsearch' | 'opensearch' | 'pgvector';
    endpoint: string;
    apiKey: string;
    apiKeyMasked?: string;
    collectionName: string;
    distanceMetric: 'cosine' | 'dot' | 'l2';
    tenantIsolation: boolean;
    recreateIndexAllowed: boolean;
  };
  retrieval: {
    mode: 'vector' | 'hybrid';
    topN: number;
    candidateTopK: number;
    scoreThreshold: number;
    metadataFiltersEnabled: boolean;
    maxChunksPerDocument: number;
    dedupByDocument: boolean;
    hybrid: {
      vectorWeight: number;
      keywordWeight: number;
      fusionMethod: 'rrf' | 'weighted';
      rrfK: number;
      keywordAnalyzer: 'standard' | 'cjk' | 'ik';
      keywordTopK: number;
    };
    rerank: {
      enabled: boolean;
      provider: 'model_center';
      modelInstanceId: string;
      model: string;
      endpoint: string;
      topK: number;
      scoreThreshold: number;
      timeoutSeconds: number;
      fallbackPolicy: 'return_vector_results' | 'return_empty' | 'fail';
    };
  };
  context: {
    includeTitlePath: boolean;
    includePageNo: boolean;
    includeDocumentMeta: boolean;
    neighborChunksBefore: number;
    neighborChunksAfter: number;
    maxContextTokens: number;
  };
  citation: {
    required: boolean;
    returnSourceChunks: boolean;
    returnRawChunkRefs: boolean;
    enablePageJump: boolean;
    maxCount: number;
  };
  index: {
    autoIndexAfterParse: boolean;
    batchSize: number;
    retryTimes: number;
    retryIntervalSeconds: number;
    versioningEnabled: boolean;
  };
  updatedAt: string;
}

export async function fetchKnowledgeParseSettings() {
  const { data } = await apiClient.get<KnowledgeParseSettings>('/api/settings/knowledge/parse');
  return data;
}

export async function saveKnowledgeParseSettings(payload: KnowledgeParseSettingsPayload) {
  const { data } = await apiClient.put<KnowledgeParseSettings>('/api/settings/knowledge/parse', payload);
  return data;
}

export async function fetchKnowledgeSettings() {
  const { data } = await apiClient.get<KnowledgeSettings>('/api/settings/knowledge');
  return data;
}

export async function saveKnowledgeSettings(payload: KnowledgeSettings) {
  const { updatedAt, ...body } = payload;
  void updatedAt;
  const { data } = await apiClient.put<KnowledgeSettings>('/api/settings/knowledge', body);
  return data;
}
