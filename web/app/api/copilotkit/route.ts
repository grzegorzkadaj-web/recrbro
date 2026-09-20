import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const runtime = new CopilotRuntime({
  agents: {
    recrbro_agent: new HttpAgent({
      url: `${backendUrl}/agent`,
    }),
  },
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
  mode: "single-route",
});

export const POST = handler;
