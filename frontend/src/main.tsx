import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { LoginGate } from "@/components/auth/LoginGate";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
// Оформление и тема применяются при загрузке модуля: атрибуты уже
// проставлены встроенным скриптом в index.html, здесь подхватывается
// цвет адресной строки, для которого нужны загруженные стили.
import "@/lib/theme";
import "@/lib/design";
import "@/index.css";

// Служебный работник нужен ровно для одного: без него Chrome не
// предлагает «добавить на главный экран». Регистрация не мешает
// обычной работе и молча пропускается там, где её нет, — например
// на http://localhost без TLS.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => {
      // Установка на главный экран просто не предложится. Ронять
      // из-за этого приложение незачем.
    });
  });
}

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
