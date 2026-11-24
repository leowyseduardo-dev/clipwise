import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserClipStudio } from "./components/BrowserClipStudio";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserClipStudio />
  </StrictMode>,
);
