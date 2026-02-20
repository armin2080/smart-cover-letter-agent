import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import type { LoginRequest } from "../../types/auth";
import { useLoginMutation } from "../../store/api/authApi";
import "./Login.scss";

export default function Login() {
  const navigate = useNavigate();
  const [login, { isLoading, error }] = useLoginMutation();

  const {
    register: registerField,
    handleSubmit,
    formState: { errors },
    setError,
  } = useForm<LoginRequest>({
    mode: "onBlur",
    defaultValues: {
      email: "",
      password: "",
    },
  });

  const [generalError, setGeneralError] = useState<string | null>(null);

  const onSubmit = async (data: LoginRequest) => {
    setGeneralError(null);

    try {
      const response = await login(data).unwrap();

      localStorage.setItem("accessToken", response.access);
      localStorage.setItem("refreshToken", response.refresh);

      navigate("/dashboard");
    } catch (err: unknown) {
      if (err && typeof err === "object") {
        const apiError = err as Record<string, unknown>;

        if (apiError.detail && typeof apiError.detail === "string") {
          setGeneralError(apiError.detail);
        } else if (apiError.email && Array.isArray(apiError.email)) {
          setError("email", {
            type: "manual",
            message: apiError.email[0] as string,
          });
        } else if (apiError.password && Array.isArray(apiError.password)) {
          setError("password", {
            type: "manual",
            message: apiError.password[0] as string,
          });
        } else {
          setGeneralError("Invalid email or password. Please try again.");
        }
      } else {
        setGeneralError("An error occurred. Please try again.");
      }
    }
  };
  return (
    <div className="login">
      <h1 className="login__title">Welcome back</h1>

      {(generalError || error) && (
        <Alert severity="error" className="login__alert">
          {generalError ||
            (typeof error === "object" && error !== null && "detail" in error
              ? (error.detail as string)
              : "An error occurred. Please try again.")}
        </Alert>
      )}

      <form className="login__form" onSubmit={handleSubmit(onSubmit)}>
        <div className="login__form-group">
          <label className="login__label" htmlFor="email">
            Email
          </label>
          <TextField
            id="email"
            type="email"
            variant="outlined"
            placeholder="Enter your email"
            fullWidth
            disabled={isLoading}
            error={!!errors.email}
            helperText={errors.email?.message}
            {...registerField("email", {
              required: "Email is required",
              pattern: {
                value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                message: "Please enter a valid email address",
              },
            })}
          />
        </div>

        <div className="login__form-group">
          <label className="login__label" htmlFor="password">
            Password
          </label>
          <TextField
            id="password"
            type="password"
            variant="outlined"
            placeholder="Enter your password"
            fullWidth
            disabled={isLoading}
            error={!!errors.password}
            helperText={errors.password?.message}
            {...registerField("password", {
              required: "Password is required",
            })}
          />
        </div>

        <Box className="login__button-container" position="relative">
          <Button
            type="submit"
            variant="contained"
            className="login__button"
            disabled={isLoading}
            fullWidth
          >
            {isLoading ? "Signing in..." : "Log In"}
          </Button>
          {isLoading && (
            <CircularProgress
              size={24}
              sx={{
                position: "absolute",
                top: "50%",
                left: "50%",
                marginTop: "-12px",
                marginLeft: "-12px",
              }}
            />
          )}
        </Box>
      </form>

      <div className="login__footer">
        <p className="login__footer-text">
          Don't have an account?{" "}
          <Link to="/signup" className="login__footer-link">
            Sign Up
          </Link>
        </p>
      </div>
    </div>
  );
}
