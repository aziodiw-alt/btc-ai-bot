/*
 * Безопасная проверка чтения последних Spot-сделок BTC/USDT с Bybit EU.
 *
 * Запуск:
 *   node test_bybit_trades.js
 *
 * Скрипт только читает историю исполнений.
 * Он не содержит команд создания, изменения или отмены ордеров.
 */

const fs = require("fs");
const path = require("path");
const { RestClientV5 } = require("bybit-api");


function loadEnvFile() {
  const envPath = path.join(__dirname, ".env");

  if (!fs.existsSync(envPath)) {
    throw new Error("Файл .env не найден рядом с test_bybit_trades.js");
  }

  const lines = fs.readFileSync(envPath, "utf8").replace(/^\uFEFF/, "").split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separator = trimmed.indexOf("=");

    if (separator === -1) {
      continue;
    }

    const key = trimmed.slice(0, separator).trim();
    let value = trimmed.slice(separator + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}


function formatDate(timestamp) {
  return new Date(Number(timestamp)).toLocaleString("ru-RU");
}


async function main() {
  loadEnvFile();

  const key = process.env.BYBIT_API_KEY;
  const secret = process.env.BYBIT_API_SECRET;

  if (!key || !secret) {
    throw new Error(
      "Добавьте BYBIT_API_KEY и BYBIT_API_SECRET в файл .env"
    );
  }

  const client = new RestClientV5({
    key,
    secret,
    apiRegion: "EU",
  });

  console.log("Получаю последние Spot-сделки BTC/USDT с Bybit EU...\n");

  const response = await client.getExecutionList({
    category: "spot",
    symbol: "BTCUSDT",
    limit: 5,
  });

  if (response.retCode !== 0) {
    throw new Error(`Bybit: ${response.retMsg} (код ${response.retCode})`);
  }

  const trades = response.result?.list || [];

  if (trades.length === 0) {
    console.log("Сделки BTC/USDT не найдены.");
    return;
  }

  console.log(`Найдено сделок: ${trades.length}\n`);

  trades.forEach((trade, index) => {
    console.log(`Сделка ${index + 1}`);
    console.log(`Дата: ${formatDate(trade.execTime)}`);
    console.log(`Сторона: ${trade.side === "Buy" ? "Покупка" : "Продажа"}`);
    console.log(`Цена: ${trade.execPrice}`);
    console.log(`Количество BTC: ${trade.execQty}`);
    console.log(`Сумма: ${trade.execValue}`);
    console.log(`Комиссия: ${trade.execFee} ${trade.feeCurrency || ""}`);
    console.log(`Тип: ${trade.isMaker ? "Maker" : "Taker"}`);
    console.log("");
  });

  console.log("Проверка завершена успешно ✅");
}


main().catch((error) => {
  console.error("Ошибка проверки Bybit:");
  console.error(error.message || error);
  console.error(
    "\nПроверьте ключи в .env, разрешение Read-Only Spot Trade " +
      "и выбор приложения Siebly SDKs."
  );
  process.exitCode = 1;
});
