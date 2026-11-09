/**
 * DP4500 Biometric Client for JavaScript / TypeScript
 * Compatible with Browser (Vanilla JS, React, Vue, Angular) and Node.js (v18+).
 * Communicates with the dp4500 FastAPI service (examples/04_fastapi_rest_service.py).
 */

class DP4500Client {
  /**
   * @param {string} baseUrl - Base URL of the Python API service (default: http://127.0.0.1:8000)
   */
  constructor(baseUrl = "http://127.0.0.1:8000") {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  /**
   * Check connected fingerprint readers and system health.
   * @returns {Promise<Array<{name: string, driver: string, device_id: string, vendor_id: string, product_id: string}>>}
   */
  async getStatus() {
    const response = await fetch(`${this.baseUrl}/health`);
    if (!response.ok) {
      throw new Error(`Failed to check reader status: ${response.statusText}`);
    }
    return await response.json();
  }

  /**
   * Capture a single live fingerprint scan.
   * Blocks until a finger touches the sensor.
   * @returns {Promise<{width: number, height: number, dpi: number, quality_score: number, image_base64: string}>}
   */
  async scan() {
    const response = await fetch(`${this.baseUrl}/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errData.detail || "Fingerprint scan failed");
    }

    return await response.json();
  }

  /**
   * Perform multi-stage enrollment for a user and return the biometric template.
   * @param {string} username - User identifier
   * @param {string} fingerName - Name of the finger (default: 'right_index')
   * @param {number} stages - Number of touches required (default: 5)
   * @returns {Promise<{username: string, finger_name: string, template_base64: string, template_size: number}>}
   */
  async enroll(username, fingerName = "right_index", stages = 5) {
    const response = await fetch(`${this.baseUrl}/enroll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: username,
        finger_name: fingerName,
        stages: stages,
      }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errData.detail || "Enrollment failed");
    }

    return await response.json();
  }

  /**
   * Perform 1:1 biometric verification of the live finger against an enrolled template.
   * @param {string} templateBase64 - Enrolled template in Base64 format
   * @returns {Promise<{matched: boolean, score: number}>}
   */
  async verify(templateBase64) {
    const response = await fetch(`${this.baseUrl}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template_base64: templateBase64,
      }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errData.detail || "Verification failed");
    }

    return await response.json();
  }

  /**
   * Perform 1:N identification: matches the live finger against an array of candidate templates.
   * @param {Array<{user_id: string, template_base64: string}>} candidates
   * @returns {Promise<{matched: boolean, user_id: string|null, score: number}>}
   */
  async identify(candidates) {
    const response = await fetch(`${this.baseUrl}/identify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        candidates: candidates,
      }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errData.detail || "Identification failed");
    }

    return await response.json();
  }
}

// Support both ES module and CommonJS / Browser script tags
if (typeof module !== "undefined" && module.exports) {
  module.exports = { DP4500Client };
} else if (typeof window !== "undefined") {
  window.DP4500Client = DP4500Client;
}
