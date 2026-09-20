import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export async function POST(request: Request) {
  const authorization = request.headers.get("authorization");
  if (!authorization) {
    return Response.json({ error: "Sign in to use the assistant." }, { status: 401 });
  }

  const verification = await fetch(`${backendUrl}/api/me`, {
    headers: { Authorization: authorization },
    cache: "no-store",
  });
  if (!verification.ok) {
    return Response.json({ error: "Your session is invalid or expired." }, { status: 401 });
  }

  const runtime = new CopilotRuntime({
    agents: {
      recrbro_agent: new HttpAgent({
        url: `${backendUrl}/agent`,
        headers: { Authorization: authorization },
      }),
    },
  });
  return createCopilotRuntimeHandler({
    runtime,
    basePath: "/api/copilotkit",
    mode: "single-route",
  })(request);
}
