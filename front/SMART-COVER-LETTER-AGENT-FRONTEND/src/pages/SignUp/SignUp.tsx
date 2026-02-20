import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import type { RegisterRequest } from "../../types/auth";
import { useRegisterMutation } from "../../store/api/authApi";
import "./SignUp.scss";

export default function SignUp() {
  const navigate = useNavigate();

  const [register, { isLoading, error }] = useRegisterMutation();

  const {
    register: registerField,
    handleSubmit,
    watch,
    formState: { errors },
    setError,
  } = useForm<RegisterRequest>({
    mode: "onBlur",
    defaultValues: {
      email: "",
      password: "",
      password2: "",
    },
  });

  const password = watch("password");

  const [generalError, setGeneralError] = useState<string | null>(null);

  const onSubmit = async (data: RegisterRequest) => {
    setGeneralError(null);

    if (data.password !== data.password2) {
      setError("password2", {
        type: "manual",
        message: "Passwords do not match",
      });
      return;
    }

    try {
      const response = await register(data).unwrap();

      localStorage.setItem("accessToken", response.access);
      localStorage.setItem("refreshToken", response.refresh);
      localStorage.setItem("user", JSON.stringify(response.user));

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
        } else {
          setGeneralError("An error occurred. Please try again.");
        }
      }
    }
  };

  return (
    <div className="sign-up">
      <h1 className="sign-up__title">Create your account</h1>

      {(generalError || error) && (
        <Alert severity="error" className="sign-up__alert">
          {generalError ||
            (typeof error === "object" && error !== null && "detail" in error
              ? (error.detail as string)
              : "An error occurred. Please try again.")}
        </Alert>
      )}

      <form className="sign-up__form" onSubmit={handleSubmit(onSubmit)}>
        <div className="sign-up__form-group">
          <label className="sign-up__label" htmlFor="email">
            Email
          </label>
          <TextField
            id="email"
            type="email"
            variant="outlined"
            placeholder="jane@example.com"
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

        <div className="sign-up__form-group">
          <label className="sign-up__label" htmlFor="password">
            Password
          </label>
          <TextField
            id="password"
            type="password"
            variant="outlined"
            placeholder="Create a strong password"
            fullWidth
            disabled={isLoading}
            error={!!errors.password}
            helperText={errors.password?.message}
            {...registerField("password", {
              required: "Password is required",
              minLength: {
                value: 8,
                message: "Password must be at least 8 characters",
              },
            })}
          />
        </div>

        <div className="sign-up__form-group">
          <label className="sign-up__label" htmlFor="password2">
            Confirm Password
          </label>
          <TextField
            id="password2"
            type="password"
            variant="outlined"
            placeholder="Confirm your password"
            fullWidth
            disabled={isLoading}
            error={!!errors.password2}
            helperText={
              errors.password2?.message ||
              (password && !errors.password2
                ? "Passwords match ✓"
                : "Enter your password again")
            }
            {...registerField("password2", {
              required: "Please confirm your password",
              validate: (value) =>
                value === password || "Passwords do not match",
            })}
          />
        </div>

        <Box className="sign-up__button-container" position="relative">
          <Button
            type="submit"
            variant="contained"
            className="sign-up__button"
            disabled={isLoading}
            fullWidth
          >
            {isLoading ? "Creating account..." : "Sign Up"}
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

      <div className="sign-up__footer">
        <p className="sign-up__footer-text">
          Already have an account?{" "}
          <Link to="/login" className="sign-up__footer-link">
            Log In
          </Link>
        </p>
      </div>
    </div>
  );
}
