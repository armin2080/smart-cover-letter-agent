import { Link } from "react-router-dom";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import "./Login.scss";

export default function Login() {
  return (
    <div className="login">
      <h1 className="login__title">Welcome back</h1>

      <form className="login__form">
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
          />
        </div>

        <Button type="submit" variant="contained" className="login__button">
          Log In
        </Button>
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
