import { Link } from "react-router-dom";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import "./SignUp.scss";

export default function SignUp() {
  return (
    <div className="sign-up">
      <h1 className="sign-up__title">Create your account</h1>

      <form className="sign-up__form">
        <div className="sign-up__form-row">
          <div className="sign-up__form-group">
            <label className="sign-up__label" htmlFor="firstName">
              First Name
            </label>
            <TextField
              id="firstName"
              variant="outlined"
              placeholder="Jane"
              fullWidth
            />
          </div>

          <div className="sign-up__form-group">
            <label className="sign-up__label" htmlFor="lastName">
              Last Name
            </label>
            <TextField
              id="lastName"
              variant="outlined"
              placeholder="Doe"
              fullWidth
            />
          </div>
        </div>

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
          />
        </div>

        <Button type="submit" variant="contained" className="sign-up__button">
          Sign Up
        </Button>
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
