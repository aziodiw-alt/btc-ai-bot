import base64
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


def _extract_json(text):
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)

    if not isinstance(data, list):
        raise ValueError("AI вернул данные в неизвестном формате.")

    return data


def parse_orders(image_file=None, copied_text=""):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY не найден в файле .env.")

    copied_text = (copied_text or "").strip()
    content = [
        {
            "type": "input_text",
            "text": (
                "Извлеки все открытые Spot Limit ордера BTC/USDT и ETH/USDT. "
                "Верни только JSON-массив без Markdown. Каждый элемент: "
                '{"symbol":"BTCUSDT или ETHUSDT","side":"BUY или SELL",'
                '"order_type":"LIMIT","order_value":число,'
                '"order_price":число,"order_quantity":число,'
                '"created_at":"YYYY-MM-DDTHH:MM","order_id":"строка"}. '
                "Обязательно проверь: order_price × order_quantity должно "
                "примерно равняться order_value. Не меняй местами цену и сумму. "
                "Не выдумывай отсутствующие значения. "
                "Если значение не видно, используй пустую строку или 0."
            ),
        }
    ]

    if copied_text:
        content.append(
            {
                "type": "input_text",
                "text": "Скопированный текст из Bybit:\n" + copied_text,
            }
        )

    if image_file and image_file.filename:
        image_bytes = image_file.read()
        if not image_bytes:
            raise ValueError("Загруженный скриншот пуст.")

        mime_type = image_file.mimetype or "image/png"
        image_url = (
            f"data:{mime_type};base64,"
            + base64.b64encode(image_bytes).decode("ascii")
        )
        content.append(
            {
                "type": "input_image",
                "image_url": image_url,
            }
        )

    if len(content) == 1:
        raise ValueError("Загрузите скриншот или вставьте строку ордера.")

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("OPENAI_VISION_MODEL", "gpt-5-mini"),
        input=[{"role": "user", "content": content}],
    )
    orders = _extract_json(response.output_text)

    if not orders:
        raise ValueError("На изображении не найдено открытых ордеров.")

    return orders
