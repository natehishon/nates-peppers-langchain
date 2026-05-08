import axios from 'axios';

const API_BASE = "http://127.0.0.1:8000";

export interface Order {
  id: string;
  customer_name: string;
  pepper_variety?: string;
  status: string;
  created_at: string;
}

export const startAudit = async (formData: FormData) => {
  const response = await fetch(`${API_BASE}/audit/start`, {
    method: 'POST',
    body: formData,
  });
  return response.json();
};

export const fetchOrders = async (): Promise<Order[]> => {
  const res = await axios.get(`${API_BASE}/orders`);
  return res.data;
};

export const resumeOrder = async (threadId: string, decision: string) => {
  const res = await axios.post(`${API_BASE}/audit/${threadId}/resume?human_decision=${decision}`);
  return res.data;
};
