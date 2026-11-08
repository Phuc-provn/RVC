export interface Voice {
  id: string;
  name: string;
  speaker_name: string;
}

export interface VoicesResponse {
  default_model: string;
  voices: Voice[];
}

const BASE_URL = (import.meta as any).env?.VITE_BACKEND_URL
  ? (import.meta as any).env.VITE_BACKEND_URL.replace(/\/$/, '')
  : '';

export async function fetchVoices(): Promise<VoicesResponse> {
  const res = await fetch(`${BASE_URL}/api/voices`);
  if (!res.ok) {
    throw new Error(`Failed to fetch voices: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/api/health`);
    return res.ok;
  } catch {
    return false;
  }
}
