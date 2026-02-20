import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import type {
  RegisterRequest,
  RegisterResponse,
  LoginRequest,
  LoginResponse,
  LogoutRequest,
  LogoutResponse,
  RefreshTokenRequest,
  RefreshTokenResponse,
  ProfileResponse,
} from "../../types/auth";

const API_BASE_URL = import.meta.env.VITE_API_URL;

export const authApi = createApi({
  reducerPath: "authApi",

  baseQuery: fetchBaseQuery({
    baseUrl: API_BASE_URL,
    prepareHeaders: (headers, { getState }: any) => {
      const token = getState().auth?.accessToken;
      if (token) {
        headers.set("authorization", `Bearer ${token}`);
      }
      return headers;
    },
  }),

  endpoints: (builder) => ({
    register: builder.mutation<RegisterResponse, RegisterRequest>({
      query: (credentials) => ({
        url: "/api/register/",
        method: "POST",
        body: credentials,
      }),
    }),

    login: builder.mutation<LoginResponse, LoginRequest>({
      query: (credentials) => ({
        url: "/api/login/",
        method: "POST",
        body: credentials,
      }),
    }),

    logout: builder.mutation<LogoutResponse, LogoutRequest>({
      query: (data) => ({
        url: "/api/logout/",
        method: "POST",
        body: data,
      }),
    }),

    refreshToken: builder.mutation<RefreshTokenResponse, RefreshTokenRequest>({
      query: (data) => ({
        url: "/api/token/refresh/",
        method: "POST",
        body: data,
      }),
    }),

    getProfile: builder.query<ProfileResponse, void>({
      query: () => "/api/profile/",
    }),

    updateProfile: builder.mutation<
      { success: boolean },
      Partial<ProfileResponse>
    >({
      query: (data) => ({
        url: "/api/profile/",
        method: "PUT",
        body: data,
      }),
    }),
  }),
});

export const {
  useRegisterMutation,
  useLoginMutation,
  useLogoutMutation,
  useRefreshTokenMutation,
  useGetProfileQuery,
  useUpdateProfileMutation,
} = authApi;
