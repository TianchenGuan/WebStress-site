import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./index.css";

import Layout from "./components/Layout";
import Home from "./routes/Home";
import Tasks from "./routes/Tasks";
import TaskDetail from "./routes/TaskDetail";
import Primitives from "./routes/Primitives";
import PrimitiveDetail from "./routes/PrimitiveDetail";
import Environments from "./routes/Environments";
import EnvironmentDetail from "./routes/EnvironmentDetail";
import Results from "./routes/Results";
import Docs from "./routes/Docs";
import DocsSetup from "./routes/DocsSetup";
import NotFound from "./routes/NotFound";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/tasks/:taskId" element={<TaskDetail />} />
          <Route path="/primitives" element={<Primitives />} />
          <Route path="/primitives/:primitive" element={<PrimitiveDetail />} />
          <Route path="/environments" element={<Environments />} />
          <Route path="/environments/:env" element={<EnvironmentDetail />} />
          <Route path="/results" element={<Results />} />
          <Route path="/docs" element={<Docs />} />
          <Route path="/docs/setup" element={<DocsSetup />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
