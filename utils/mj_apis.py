import logging
import re
import aiohttp
import json

from utils import db
from config import go_api_token, APIFRAME_API_KEY, midjourney_webhook_url, LEGNEXT_API_KEY

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d #%(levelname)-8s '
           '[%(asctime)s] - %(name)s - %(message)s')

GOAPI_URL = "https://api.goapi.ai/mj/v2"
APIFRAME_URL = "https://api.apiframe.pro"
LEGNEXT_URL = "https://api.legnext.ai/api/v1"

GOAPI_HEADERS = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-API-KEY': go_api_token
}

APIFRAME_HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': APIFRAME_API_KEY
}

LEGNEXT_HEADERS = {
    'Content-Type': 'application/json',
    'x-api-key': LEGNEXT_API_KEY
}

# Любые --флаги (для очистки ПОЛЬЗОВАТЕЛЬСКОГО ввода до отправки в GPT)
_ANY_FLAG_RE = re.compile(r'--\S+(?:\s+\S+)?', re.IGNORECASE)

# Флаги, удалённые в MJ v8.1 + флаг версии --v (бот сам подставит --v 8.1)
# (?!--) — значение флага не должно начинаться с --, иначе захватит соседний флаг
_V81_BANNED_FLAGS_RE = re.compile(
    r'--(?:quality|cref|cw|oref|ow|version|no|q|v)\b(?:\s+(?!--)\S+)?', re.IGNORECASE
)


def _strip_user_flags(text: str) -> str:
    """Вырезает любые --флаги из пользовательского ввода. Юзер не управляет флагами — их подбирает GPT."""
    return _ANY_FLAG_RE.sub('', text).strip()


def _strip_v81_banned_flags(text: str) -> str:
    return _V81_BANNED_FLAGS_RE.sub('', text).strip()


# Хранилище для retry-логики: action_id -> {'prompt': enhanced_prompt, 'count': retry_count}
# Живёт в памяти процесса. При перезапуске бота state теряется (это ОК для коротких задач MJ).
_retry_state: dict = {}

# Максимум повторных попыток (не считая первую)
MJ_MAX_RETRIES = 2


def is_temporary_mj_error(message) -> bool:
    """Временная ошибка — таймаут, перегрузка, недоступность ботов. Имеет смысл ретраить."""
    if not message:
        return False
    msg = str(message).lower()
    return any(k in msg for k in ['timeout', 'callback and fetch', 'bot is inactive',
                                   'no available bot', 'service unavailable', 'overloaded',
                                   'rate limit', 'too many requests'])


def friendly_mj_error(raw_message) -> str:
    """Преобразует техническое сообщение об ошибке MJ/Legnext в понятное пользователю."""
    if not raw_message:
        return "⏳ Сервис Midjourney временно недоступен. Попробуйте через минуту."

    msg = str(raw_message).lower()

    if any(k in msg for k in ['timeout', 'callback and fetch', 'bot is inactive',
                               'no available bot', 'service unavailable', 'overloaded',
                               'rate limit', 'too many requests']):
        return "⏳ Сервис Midjourney перегружен. Попробуйте через минуту."

    if any(k in msg for k in ['invalid prompt', 'invalid request', 'parse error',
                               'malformed', 'invalid parameter']):
        return "⚠️ Не удалось обработать запрос. Попробуйте переформулировать."

    if any(k in msg for k in ['banned', 'prohibit', 'forbidden', 'content policy', 'nsfw']):
        return "🚫 Запрос содержит запрещённые слова. Попробуйте переформулировать."

    if any(k in msg for k in ['unsupported task type', 'piapi_v8', 'not supported']):
        return "⚠️ Эта функция временно недоступна для текущей версии Midjourney."

    return "⏳ Не удалось сгенерировать изображение. Попробуйте через минуту."


class GoAPI:
    def __init__(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        await self.session.close()

    async def create_request(self, data, action, request_id):
        data["webhook_endpoint"] = midjourney_webhook_url + "/" + str(request_id)
        data["notify_progress"] = True
        url = f"{GOAPI_URL}/{action}"

        logger.info(f"Отправка запроса к GoAPI: URL={url}, Data={data}")

        try:
            async with self.session.post(url, json=data, headers=GOAPI_HEADERS) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Ошибка GoAPI: {response.status} - {error_text}")
                    raise Exception(f"GoAPI Error: {response.status} - {error_text}")
                response_content = await response.json()
                logger.info(f"Ответ GoAPI: {response_content}")

                task_id = response_content.get('task_id')
                if task_id:
                    logger.info(f"Task ID: {task_id}, Request ID: {request_id}")
                    await db.update_action_with_task_id(request_id, task_id)

                return response_content
        except Exception as e:
            logger.info(f"Ошибка при запросе к GoAPI: {e}")
            raise

    async def imagine(self, prompt, request_id):
        data = {
            "process_mode": "fast",
            "prompt": prompt,
        }
        return await self.create_request(data, "imagine", request_id)

    async def upscale(self, task_id, index, request_id):
        data = {
            "origin_task_id": task_id,
            "index": index
        }
        return await self.create_request(data, "upscale", request_id)

    async def variation(self, task_id, index, request_id):
        data = {
            "origin_task_id": task_id,
            "index": index
        }
        return await self.create_request(data, "variation", request_id)

    async def outpaint(self, task_id, zoom_ratio, request_id):
        data = {
            "origin_task_id": task_id,
            "zoom_ratio": zoom_ratio
        }
        return await self.create_request(data, "outpaint", request_id)


class ApiFrame:
    def __init__(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        await self.session.close()

    async def create_request(self, data, action, request_id):
        data["webhook_endpoint"] = f"{midjourney_webhook_url}"
        data["notify_progress"] = True
        url = f"{APIFRAME_URL}/{action}"

        logger.info(f'Data: {data}, Action: {action}, Request ID: {request_id}')
        logger.info(f'WebHook: {data["webhook_endpoint"]}, URL: {url}')

        try:
            async with self.session.post(url, json=data, headers=APIFRAME_HEADERS) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ошибка ApiFrame: {response.status} - {error_text}")
                    raise Exception(f"ApiFrame Error: {response.status} - {error_text}")
                response_content = await response.json()
                logger.info(f"Ответ ApiFrame: {response_content}")

                task_id = response_content.get('task_id')
                if task_id:
                    logger.info(f"Task ID: {task_id}, Request ID: {request_id}")
                    await db.update_action_with_task_id(request_id, task_id)

                return response_content
        except Exception as e:
            logger.error(f"Ошибка при запросе к ApiFrame: {e}")
            raise

    async def imagine(self, prompt, request_id):
        data = {
            "prompt": prompt,
        }
        return await self.create_request(data, "imagine", request_id)

    async def upscale(self, task_id, index, request_id):
        data = {
            "parent_task_id": task_id,
            "index": index
        }
        return await self.create_request(data, "upscale", request_id)

    async def variation(self, task_id, index, request_id):
        data = {
            "parent_task_id": task_id,
            "index": index
        }
        return await self.create_request(data, "variation", request_id)

    async def outpaint(self, task_id, zoom_ratio, request_id):
        data = {
            "parent_task_id": task_id,
            "zoom_ratio": zoom_ratio
        }
        return await self.create_request(data, "outpaint", request_id)


class LegnextAPI:
    def __init__(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        await self.session.close()

    async def create_request(self, data, action, request_id):
        data["callback"] = midjourney_webhook_url + "/" + str(request_id)
        url = f"{LEGNEXT_URL}/{action}"

        logger.info(f"Отправка запроса к Legnext: URL={url}, Data={data}")

        try:
            async with self.session.post(url, json=data, headers=LEGNEXT_HEADERS) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ошибка Legnext: {response.status} - {error_text}")
                    raise Exception(f"Legnext Error: {response.status} - {error_text}")
                response_content = await response.json()
                logger.info(f"Ответ Legnext: {response_content}")

                job_id = response_content.get('job_id')
                if job_id:
                    logger.info(f"Job ID: {job_id}, Request ID: {request_id}")
                    await db.update_action_with_task_id(request_id, job_id)

                return response_content
        except Exception as e:
            logger.error(f"Ошибка при запросе к Legnext: {e}")
            raise

    async def imagine(self, prompt, request_id):
        clean = _strip_v81_banned_flags(prompt)
        data = {"text": f"{clean} --v 8.1"}
        return await self.create_request(data, "diffusion", request_id)

    async def upscale(self, task_id, index, request_id):
        # index приходит как "1"/"2"/"3"/"4", Legnext ждёт imageNo 0-3
        try:
            image_no = int(index) - 1
        except (ValueError, TypeError):
            image_no = 0
        data = {"jobId": task_id, "imageNo": image_no, "type": 0}
        return await self.create_request(data, "upscale", request_id)

    async def variation(self, task_id, index, request_id):
        # high → type=1 (Strong), low → type=0 (Subtle)
        # если index числовой — берём первый вариант (imageNo 0)
        if str(index).lstrip('-').isdigit():
            try:
                image_no = int(index) - 1
            except (ValueError, TypeError):
                image_no = 0
            var_type = 1
        else:
            image_no = 0
            var_type = 1 if index == 'high' else 0
        data = {"jobId": task_id, "imageNo": image_no, "type": var_type}
        return await self.create_request(data, "variation", request_id)

    async def outpaint(self, task_id, zoom_ratio, request_id):
        try:
            zoom = float(zoom_ratio)
        except (ValueError, TypeError):
            zoom = 1.5
        data = {"jobId": task_id, "scale": zoom}
        return await self.create_request(data, "outpaint", request_id)


class MidJourneyAPI:
    def __init__(self, primary_api="goapi"):
        self.primary_api = primary_api  # "goapi", "apiframe" или "legnext"
        self.apiframe = ApiFrame()
        self.goapi = GoAPI()
        self.legnext = LegnextAPI()

    def set_primary_api(self, api_type):
        if api_type not in ["goapi", "apiframe", "legnext"]:
            raise ValueError("Неподдерживаемый тип API")
        self.primary_api = api_type

    async def close(self):
        await self.apiframe.close()
        await self.goapi.close()
        await self.legnext.close()

    async def create_request(self, data, action, request_id):
        logger.info(f'Data: {data}, Action: {action}, Request ID: {request_id}')

        if self.primary_api == "goapi":
            try:
                return await self.goapi.create_request(data, action, request_id)
            except Exception as e:
                logger.error(f"GoAPI недоступен: {e}.")
                try:
                    error_data = json.loads((str(e)[19:]).strip())
                    logger.info(f"Ошибка GoAPI: {error_data}")
                    return error_data
                except (json.JSONDecodeError, IndexError) as parse_error:
                    logger.error(f"Ошибка при парсинге ответа GoAPI: {parse_error}")
                    return str(e)

        if self.primary_api == "apiframe":
            try:
                return await self.apiframe.create_request(data, action, request_id)
            except Exception as e:
                logger.error(f"ApiFrame недоступен: {e}.")

        if self.primary_api == "legnext":
            try:
                return await self.legnext.create_request(data, action, request_id)
            except Exception as e:
                logger.error(f"Legnext недоступен: {e}.")
                try:
                    error_data = json.loads((str(e)[18:]).strip())
                    return error_data
                except (json.JSONDecodeError, IndexError):
                    return str(e)

    async def imagine(self, prompt, request_id):
        if self.primary_api == "goapi":
            data = {
                "process_mode": "fast",
                "prompt": prompt,
                "model_version": "v7"
            }
            return await self.create_request(data, "imagine", request_id)
        elif self.primary_api == "legnext":
            return await self.legnext.imagine(prompt, request_id)
        else:
            data = {"prompt": prompt}
            return await self.create_request(data, "imagine", request_id)

    async def upscale(self, task_id, index, request_id):
        if self.primary_api == "legnext":
            return await self.legnext.upscale(task_id, index, request_id)

        action = "upscale" if self.primary_api == "goapi" else "upscale-1x"
        if self.primary_api == "goapi":
            data = {"origin_task_id": task_id, "index": index}
        else:
            data = {"parent_task_id": task_id, "index": index}
        return await self.create_request(data, action, request_id)

    async def variation(self, task_id, index, request_id):
        if self.primary_api == "legnext":
            return await self.legnext.variation(task_id, index, request_id)

        if index == 'high':
            index = 'high_variation' if self.primary_api == "goapi" else 'strong'
        elif index == 'low':
            index = 'low_variation' if self.primary_api == "goapi" else 'subtle'

        action = "variation" if self.primary_api == "goapi" else "variations"
        if self.primary_api == "goapi":
            data = {"origin_task_id": task_id, "index": index}
        else:
            data = {"parent_task_id": task_id, "index": index}
        return await self.create_request(data, action, request_id)

    async def outpaint(self, task_id, zoom_ratio, request_id):
        if self.primary_api == "legnext":
            return await self.legnext.outpaint(task_id, zoom_ratio, request_id)

        if zoom_ratio == '1.5':
            zoom_ratio = '1.5' if self.primary_api == "goapi" else 1.5
        elif zoom_ratio == '2':
            zoom_ratio = '2' if self.primary_api == "goapi" else 2

        action = "outpaint"
        if self.primary_api == "goapi":
            data = {"origin_task_id": task_id, "zoom_ratio": zoom_ratio}
        else:
            data = {"parent_task_id": task_id, "zoom_ratio": zoom_ratio}
        return await self.create_request(data, action, request_id)
