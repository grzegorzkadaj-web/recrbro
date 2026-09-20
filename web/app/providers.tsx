"use client";

import {
  CopilotKitProvider,
  CopilotSidebar,
} from "@copilotkit/react-core/v2";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      agentId="recrbro_agent"
      useSingleEndpoint
      headers={() => {
        if (typeof window === "undefined") return {};
        const token = window.localStorage.getItem("recrbro_session");
        const headers: Record<string, string> = {};
        if (token) headers.Authorization = `Bearer ${token}`;
        return headers;
      }}
    >
      {children}
      <CopilotSidebar
        defaultOpen={false}
        width="420px"
        labels={{
          modalHeaderTitle: "Search copilot",
          chatInputPlaceholder: "Ask me to refine your search...",
        }}
      />
    </CopilotKitProvider>
  );
}
