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
