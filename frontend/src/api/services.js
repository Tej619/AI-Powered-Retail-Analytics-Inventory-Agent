import client from './client';

export const chatWithAgent = (message, sessionId = 'default-session') =>
  client.post('/chat/', { message, session_id: sessionId });

export const getInventorySummary = () => client.get('/inventory/summary');

export const getLowStockAlerts = () => client.get('/inventory/alerts/low-stock');

export const generateForecast = (productId, horizon = 14) =>
  client.post('/forecasting/generate', {
    product_id: productId,
    method: 'ai_forecast',
    horizon_days: horizon,
  });

export const extractFromReport = (text, source = 'manual_input') =>
  client.post('/insights/extract', { raw_text: text, source });