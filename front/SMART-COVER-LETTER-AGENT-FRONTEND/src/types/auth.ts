export interface RegisterRequest {
  email: string;
  password: string;
  password2: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LogoutRequest {
  refresh: string;
}

export interface RefreshTokenRequest {
  refresh: string;
}

export interface UserProfile {
  id: number;
  email: string;
  experience: string;
  skills: string[];
  certificates: string[];
  preferred_jobs: string;
}

export interface RegisterResponse {
  user: UserProfile;
  refresh: string;
  access: string;
}

export interface LoginResponse {
  refresh: string;
  access: string;
}

export interface LogoutResponse {
  success: boolean;
}

export interface RefreshTokenResponse {
  access: string;
}

export interface ProfileResponse {
  experience: string;
  skills: string[];
  certificates: string[];
  preferred_jobs: string;
}

export interface ApiError {
  detail?: string;
  [key: string]: unknown;
}
