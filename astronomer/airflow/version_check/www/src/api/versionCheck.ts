/*!
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import axios from "axios";

export type WarningType = "eom" | "eobs" | "yanked";
export type WarningLevel = "warning" | "critical";

export interface VersionWarning {
  type: WarningType;
  level: WarningLevel;
  message: string;
  days_remaining: number | null;
  dismissed_until: string | null;
  can_dismiss: boolean;
}

export interface VersionStatus {
  current_version: string | null;
  warning: VersionWarning | null;
}

export interface StatusResponse {
  status: VersionStatus;
  eom_dismissal_period_days: number;
  eobs_dismissal_period_days: number;
}

export interface DismissResponse {
  success: boolean;
  dismissed_until: string | null;
  message: string;
}

// Get base URL from the HTML base tag (set by Airflow)
const getBaseUrl = (): string => {
  const baseHref = document.querySelector("head > base")?.getAttribute("href") ?? "";
  const baseUrl = new URL(baseHref, globalThis.location.origin);
  return baseUrl.pathname.replace(/\/$/, ""); // Remove trailing slash
};

const api = axios.create({
  baseURL: `${getBaseUrl()}/version_check/ui`,
});

export const fetchStatus = async (): Promise<StatusResponse> => {
  const response = await api.get<StatusResponse>("/status");
  return response.data;
};

export const dismissEomWarning = async (): Promise<DismissResponse> => {
  const response = await api.post<DismissResponse>("/dismiss/eom");
  return response.data;
};

export const dismissEobsWarning = async (): Promise<DismissResponse> => {
  const response = await api.post<DismissResponse>("/dismiss/eobs");
  return response.data;
};
