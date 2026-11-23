import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { AccountGate } from "./components/AccountGate";
import "./index.css";
import { installDownloadBridge } from "./lib/downloadBridge";

installDownloadBridge();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AccountGate><App /></AccountGate>
  </React.StrictMode>,
);
