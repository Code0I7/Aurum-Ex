import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { LoginGate } from "@/components/auth/LoginGate";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import "@/lib/theme";
import "@/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <LoginGate>
          {/* Подтверждения — окном приложения, а не браузера. Провайдер
              стоит здесь, чтобы окно рисовалось поверх любой страницы и
              переживало переходы между ними. */}
          <ConfirmProvider>
            <App />
          </ConfirmProvider>
        </LoginGate>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
);
