/**
 * Single entry point for all data access.
 *
 * Features import `api` and never reference a transport directly, so the app
 * switches between the mock data layer and the Django backend purely through
 * environment configuration.
 */

import { config } from "../lib/config"
import type { ApiSurface } from "./contract"
import { httpApi } from "./httpApi"
import { mockApi } from "./mockApi"

export type { ApiSurface, RequestOpts } from "./contract"

export const api: ApiSurface = config.useMocks ? mockApi : httpApi

/** True when the app is backed by the in-browser mock transport. */
export const isMockMode = config.useMocks
