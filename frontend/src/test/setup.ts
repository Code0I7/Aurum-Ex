/**
 * Подготовка окружения для тестов логики.
 *
 * В node нет localStorage, а модуль i18n читает из него выбранный язык
 * прямо при загрузке — без заглушки падал бы любой тест, который его
 * втягивает (а втягивает его и форматирование сумм, и цена в часах).
 *
 * Заглушка настоящая, в памяти, а не пустышка с no-op: тесты, меняющие
 * язык, должны видеть записанное значение так же, как его видит браузер.
 */
class MemoryStorage implements Storage {
  private data = new Map<string, string>();

  get length(): number {
    return this.data.size;
  }

  clear(): void {
    this.data.clear();
  }

  getItem(key: string): string | null {
    return this.data.has(key) ? (this.data.get(key) as string) : null;
  }

  key(index: number): string | null {
    return [...this.data.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.data.delete(key);
  }

  setItem(key: string, value: string): void {
    this.data.set(key, String(value));
  }
}

Object.defineProperty(globalThis, "localStorage", {
  value: new MemoryStorage(),
  writable: true,
});

Object.defineProperty(globalThis, "sessionStorage", {
  value: new MemoryStorage(),
  writable: true,
});
