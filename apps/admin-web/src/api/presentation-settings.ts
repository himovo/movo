import { apiClient } from './client';


export type PresentationGenerationMode = 'llm' | 'image_rebuild';

export interface PresentationSettings {
  configured: boolean;
  generationMode: PresentationGenerationMode;
  llmModelId: string;
  imageModelId: string;
  visionModelId: string;
  updatedAt: string;
}

export interface PresentationSettingsPayload {
  generationMode: PresentationGenerationMode;
  llmModelId: string;
  imageModelId: string;
  visionModelId: string;
}

export async function fetchPresentationSettings() {
  const { data } = await apiClient.get<PresentationSettings>('/api/settings/presentation');
  return data;
}

export async function savePresentationSettings(payload: PresentationSettingsPayload) {
  const { data } = await apiClient.put<PresentationSettings>('/api/settings/presentation', payload);
  return data;
}
