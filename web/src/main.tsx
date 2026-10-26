// Base styles load first so page styles imported inside App (e.g. agents.css) come later in the cascade.
import "./styles/tokens.css";
import "./styles/typography.css";
import "./styles/global.css";
import "./styles/app.css";
import "./styles/controls.css";
import "./styles/eduagent.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { AuthProvider } from "./auth/AuthContext";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
