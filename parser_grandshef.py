import os
import re
import json
import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import ChannelPrivateError, ChatWriteForbiddenError
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
TELEGRAM_CHANNEL = os.getenv('TELEGRAM_CHANNEL')

class TelegramRecipeParser:
    def __init__(self):
        self.client = TelegramClient('session_name', API_ID, API_HASH)
        self.recipes_file = "recipes.json"
        self.existing_recipes = []  # Кэш существующих рецептов
        self.channel_entity = None  # Сущность канала
        
        # Загружаем существующие рецепты при инициализации
        self.load_existing_recipes()
        
        # Черный список слов для отсева рекламы/розыгрышей
        self.blacklist_words = [
            'розыгрыш', 'конкурс', 'приз', 'реклама', 'скидка', 'акция', 'win', 'giveaway',
            'промокод', 'партнерка', 'мастер-класс', 'ивент', 'мероприятие', 'встреча',
            'эфир', 'трансляция', 'стрим', 'прямой эфир', 'онлайн', 'тут', 'сейчас',
            'подключайся', 'присоединяйся', 'живой', 'завершен', 'итоги', 'победитель',
            'подарки', 'бонус', 'участник', 'купить', 'заказ', 'доставка', 'магазин',
            'wildberries', 'ozon', 'market', 'shop', 'цена', 'руб', '₽', 'wb\.', 'wildberries',
            'премия', 'номинация', 'проголосовать', 'марка', 'retaste', 'народная марка',
            'поддержите', 'голосуйте', 'бренд'
        ]
        
        # Фразы, которые точно указывают на НЕ рецепт
        self.antirecipe_phrases = [
            'поддержите грандшеф',
            'проголосовать за грандшеф',
            'народная марка',
            'премия',
            'готовка даётся с трудом',
            'что делать если'
        ]
        
        # Категории/теги для автоматического определения
        self.categories = {
            'Десерты_и_сладости': ['кекс', 'торт', 'пирог', 'печенье', 'десерт', 'сладк', 'шоколад', 'ваниль'],
            'Закуски': ['чипс', 'закуск', 'снек', 'джерки', 'мясные', 'крабов', 'оладушк'],
            'Овощи_и_гарниры': ['овощ', 'гарнир', 'жульен', 'гриб', 'картошк', 'рис'],
            'Основные_блюда': ['курин', 'мясо', 'рыб', 'говядин', 'свинин', 'грудк', 'филе', 'шашлык'],
            'Супы': ['борщ', 'суп', 'харчо', 'бульон'],
            'Выпечка': ['хлеб', 'булка', 'пицц', 'булочк']
        }

    def load_existing_recipes(self):
        """Загрузка существующих рецептов из JSON"""
        if os.path.exists(self.recipes_file):
            with open(self.recipes_file, 'r', encoding='utf-8') as f:
                try:
                    self.existing_recipes = json.load(f)
                    print(f"📋 Загружено {len(self.existing_recipes)} существующих рецептов")
                except json.JSONDecodeError:
                    print("⚠️ Ошибка чтения файла рецептов, начинаем с пустого списка")
                    self.existing_recipes = []
        else:
            self.existing_recipes = []

    def is_duplicate_recipe(self, new_recipe):
        """Проверка, является ли рецепт дубликатом по названию и содержанию"""
        new_title = new_recipe['title'].lower().strip()
        new_ingredients_count = len(new_recipe['ingredients'])
        
        for existing_recipe in self.existing_recipes:
            existing_title = existing_recipe['title'].lower().strip()
            existing_ingredients_count = len(existing_recipe['ingredients'])
            
            # Сравниваем названия (допускаем небольшие различия)
            title_similarity = self.calculate_similarity(new_title, existing_title)
            
            # Сравниваем количество ингредиентов
            ingredients_similarity = abs(new_ingredients_count - existing_ingredients_count) <= 2
            
            # Если названия очень похожи и количество ингредиентов близкое - считаем дубликатом
            if title_similarity > 0.8 and ingredients_similarity:
                return True
                
            # Дополнительная проверка: если названия идентичны
            if new_title == existing_title:
                return True
                
            # Проверка по первым 3 ингредиентам (если они совпадают, вероятно это тот же рецепт)
            if new_ingredients_count >= 3 and existing_ingredients_count >= 3:
                new_first_ingredients = [ing.lower() for ing in new_recipe['ingredients'][:3]]
                existing_first_ingredients = [ing.lower() for ing in existing_recipe['ingredients'][:3]]
                common_ingredients = set(new_first_ingredients) & set(existing_first_ingredients)
                if len(common_ingredients) >= 2:
                    return True
        
        return False

    def calculate_similarity(self, str1, str2):
        """Вычисление схожести двух строк"""
        # Простой алгоритм схожести
        str1 = re.sub(r'[^\w\s]', '', str1)
        str2 = re.sub(r'[^\w\s]', '', str2)
        
        words1 = set(str1.split())
        words2 = set(str2.split())
        
        if not words1 or not words2:
            return 0
            
        common_words = words1 & words2
        return len(common_words) / max(len(words1), len(words2))

    def save_recipe(self, recipe_data):
        """Сохранение рецепта в JSON файл с проверкой дубликатов по содержанию"""
        try:
            # Проверяем на дубликат по содержанию
            if self.is_duplicate_recipe(recipe_data):
                print(f"⚠️ Дубликат рецепта: '{recipe_data['title']}', пропускаем")
                return False
            
            # Проверяем на дубликат по ID (на всякий случай)
            if any(recipe.get('message_id') == recipe_data['message_id'] for recipe in self.existing_recipes):
                print(f"⚠️ Рецепт с ID {recipe_data['message_id']} уже существует, пропускаем")
                return False
            
            # Добавляем новый рецепт
            self.existing_recipes.append(recipe_data)
            
            # Сохраняем обратно
            with open(self.recipes_file, 'w', encoding='utf-8') as f:
                json.dump(self.existing_recipes, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Рецепт сохранен: {recipe_data['title']} (ID: {recipe_data['message_id']})")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения рецепта: {e}")
            return False

    def clean_text(self, text):
        """Улучшенная очистка текста"""
        if not text:
            return ""
        
        # Удаляем ссылки
        text = re.sub(r'https?://\S+', '', text)
        # Удаляем упоминания каналов
        text = re.sub(r'@\w+', '', text)
        # Удаляем временные метки типа [3:37]
        text = re.sub(r'\[\d{1,2}:\d{2}\]', '', text)
        # Удаляем форматирование **текст**
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        # Удаляем форматирование __текст__
        text = re.sub(r'__(.*?)__', r'\1', text)
        # Удаляем смайлики и эмодзи
        text = re.sub(r'[^\w\s.,!?;:()\-+*/°%$#@&«»"\'=]', '', text)
        # Удаляем лишние пробелы и переносы
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()
        
        return text

    def extract_title(self, text):
        """Улучшенное извлечение названия рецепта"""
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            # Пропускаем пустые строки, хештеги и короткие строки
            if not line or line.startswith('#') or len(line) < 5:
                continue
                
            # Ищем строку, которая выглядит как название рецепта
            if (len(line) > 10 and 
                not any(word in line.lower() for word in [
                    'ингредиент', 'приготовление', 'режим', 'температура', 
                    'время', 'процесс', 'шаг', 'автор'
                ]) and
                not re.search(r'\d+\s*(г|кг|мл|л|ст\.л|ч\.л|стакан|щепотк|шт)', line.lower())):
                # Очищаем от остаточного форматирования
                clean_title = re.sub(r'^#\w+', '', line)  # Удаляем хештеги в начале
                clean_title = clean_title.strip()
                if clean_title:
                    return clean_title
        
        return "Рецепт без названия"

    def extract_ingredients(self, text):
        """Извлечение ингредиентов"""
        ingredients = []
        lines = text.split('\n')
        in_ingredients = False
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Начало секции ингредиентов
            if any(word in line_lower for word in ['ингредиент', 'состав', 'продукт']):
                in_ingredients = True
                continue
            # Конец секции ингредиентов
            elif any(word in line_lower for word in ['приготовление', 'процесс', 'режим', 'шаг', 'инструкция']):
                in_ingredients = False
                continue
                
            # Собираем ингредиенты
            if in_ingredients and line.strip():
                clean_line = re.sub(r'^[•\-*\d\.\s]+', '', line.strip())
                # Проверяем, что это действительно ингредиент (содержит единицы измерения или тире)
                if (clean_line and len(clean_line) > 3 and
                    (re.search(r'\d+\s*(г|кг|мл|л|ст\.л|ч\.л|стакан|щепотк|шт|зуб|пучк)', clean_line.lower()) or
                     ' - ' in clean_line or ' – ' in clean_line)):
                    ingredients.append(clean_line)
        
        # Если не нашли по секциям, ищем по паттернам
        if len(ingredients) < 3:
            for line in lines:
                if re.search(r'\d+\s*(г|кг|мл|л|ст\.л|ч\.л|стакан|щепотк|шт|зуб|пучк)', line.lower()):
                    clean_line = re.sub(r'^[•\-*\d\.\s]+', '', line.strip())
                    if clean_line and len(clean_line) > 3 and clean_line not in ingredients:
                        ingredients.append(clean_line)
        
        return ingredients

    def extract_steps(self, text):
        """Извлечение шагов приготовления"""
        steps = []
        lines = text.split('\n')
        in_steps = False
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Начало секции приготовления
            if any(word in line_lower for word in ['приготовление', 'процесс', 'инструкция', 'шаг']):
                in_steps = True
                continue
            # Конец секции
            elif any(word in line_lower for word in ['приятного', 'аппетит', 'автор', 'чат', 'подписывайся']):
                in_steps = False
                continue
                
            if in_steps and line.strip():
                clean_step = re.sub(r'^[•\-*\d\.\s]+', '', line.strip())
                # Более строгая проверка на шаг приготовления
                if (clean_step and len(clean_step) > 15 and 
                    not any(word in clean_step.lower() for word in ['режим', 'температура', 'время']) and
                    not re.search(r'^\d+\s*$', clean_step)):
                    steps.append(clean_step)
        
        return steps

    def extract_mode_temperature_time(self, text):
        """Извлечение режима, температуры и времени"""
        mode = None
        temperature = None
        time = None
        
        # Поиск режима
        mode_match = re.search(r'режим[:\s]*([^,\n\.]+)', text, re.IGNORECASE)
        if mode_match:
            mode = re.sub(r'[^\w\s]', '', mode_match.group(1).strip())
        
        # Поиск температуры
        temp_match = re.search(r'температур[ауы]?[:\s]*(\d+\s*°?[Cc]?)', text, re.IGNORECASE)
        if not temp_match:
            temp_match = re.search(r'(\d+\s*°?[Cc]\s*)', text)
        if temp_match:
            temperature = temp_match.group(1).strip()
        
        # Поиск времени
        time_match = re.search(r'время[:\s]*([^\n\.]+)', text, re.IGNORECASE)
        if not time_match:
            time_match = re.search(r'(\d+[\d\s\-]*\s*(минут|час|ч|мин))', text, re.IGNORECASE)
        if time_match:
            time = time_match.group(1).strip()
        
        return mode, temperature, time

    def detect_tags(self, text, title):
        """Определение тегов/категорий"""
        tags = []
        combined_text = (title + ' ' + text).lower()
        
        for category, keywords in self.categories.items():
            if any(keyword in combined_text for keyword in keywords):
                tags.append(category)
        
        # Также ищем хэштеги в тексте
        hashtags = re.findall(r'#(\w+)', text)
        tags.extend(hashtags)
        
        return tags if tags else ['Основные_блюда']

    def has_blacklist_content(self, text):
        """Улучшенная проверка на содержание черного списка"""
        text_lower = text.lower()
        
        # Проверяем анти-рецепт фразы
        if any(phrase in text_lower for phrase in self.antirecipe_phrases):
            return True
        
        # Проверяем наличие черных слов
        black_words_count = sum(1 for word in self.blacklist_words if word in text_lower)
        
        if black_words_count >= 2:
            return True
            
        # Особые случаи
        special_cases = [
            'эфир завершен',
            'прямо сейчас на эфире', 
            'подключиться к эфиру',
            'итоги розыгрыша',
            'победител',
            'розыгрыш завершен',
            'наши победители',
            'народная марка'
        ]
        
        return any(case in text_lower for case in special_cases)

    def is_recipe_post(self, text):
        """Улучшенная функция определения рецепта"""
        if not text or len(text) < 150:  # Увеличили минимальную длину
            return False
            
        cleaned_text = self.clean_text(text)
        
        # Быстрая проверка на черный список
        if self.has_blacklist_content(cleaned_text):
            return False
        
        # Проверяем наличие ключевых элементов рецепта
        ingredients = self.extract_ingredients(cleaned_text)
        steps = self.extract_steps(cleaned_text)
        
        # Более строгие критерии
        has_sufficient_ingredients = len(ingredients) >= 3
        has_sufficient_steps = len(steps) >= 2
        has_cooking_terms = any(word in cleaned_text.lower() for word in [
            'нарежьте', 'варите', 'жарьте', 'запекайте', 'смешайте', 'добавьте'
        ])
        
        return has_sufficient_ingredients and has_sufficient_steps and has_cooking_terms

    def parse_recipe(self, text, message_id, post_date):
        """Основной парсер рецепта"""
        if not self.is_recipe_post(text):
            return None
            
        cleaned_text = self.clean_text(text)
        
        # Извлекаем все компоненты
        title = self.extract_title(cleaned_text)
        ingredients = self.extract_ingredients(cleaned_text)
        steps = self.extract_steps(cleaned_text)
        mode, temperature, time = self.extract_mode_temperature_time(cleaned_text)
        tags = self.detect_tags(cleaned_text, title)
        
        # Определяем for_airfryer
        for_airfryer = any(word in cleaned_text.lower() for word in ['грандшеф', 'аэрогриль', 'airfryer'])
        
        recipe_data = {
            "message_id": message_id,
            "post_date": post_date.isoformat() if post_date else None,
            "parsed_date": datetime.now().isoformat(),
            "title": title,
            "ingredients": ingredients,
            "mode": mode,
            "temperature": temperature,
            "time": time,
            "steps": steps,
            "tags": tags,
            "raw_text": cleaned_text,
            "for_airfryer": for_airfryer
        }
        
        return recipe_data

    async def setup_channel(self):
        """Подписка на канал и настройка обработчика"""
        print("🔧 Инициализация Telegram клиента...")
        
        try:
            # Запускаем клиента
            await self.client.start(phone=PHONE_NUMBER)
            print("✅ Авторизация успешна")
            
            # Получаем канал
            print(f"🔍 Поиск канала: {TELEGRAM_CHANNEL}")
            
            try:
                # Пробуем получить канал
                self.channel_entity = await self.client.get_entity(TELEGRAM_CHANNEL)
                
                # Проверяем доступ
                try:
                    # Пробуем подписаться на канал (если еще не подписаны)
                    await self.client(JoinChannelRequest(self.channel_entity))
                    print(f"✅ Подписались на канал: {self.channel_entity.title}")
                except Exception as e:
                    # Если уже подписаны или нет прав - это нормально
                    print(f"ℹ️  Уже подписаны на канал или нет прав на подписку: {e}")
                
                print(f"✅ Канал найден: {self.channel_entity.title}")
                print(f"📊 ID канала: {self.channel_entity.id}")
                
                # Проверяем последние сообщения
                print("\n🔍 Проверяем доступ к сообщениям...")
                try:
                    async for message in self.client.iter_messages(self.channel_entity, limit=2):
                        print(f"📨 Последнее сообщение {message.id}: {message.text[:50] if message.text else 'Медиа'}")
                except Exception as e:
                    print(f"⚠️ Не удалось получить сообщения: {e}")
                
                return self.channel_entity
                
            except (ValueError, ChannelPrivateError) as e:
                print(f"❌ Ошибка доступа к каналу: {e}")
                print("Возможные причины:")
                print("1. Вы не подписаны на приватный канал")
                print("2. Указан неверный username или ID")
                print("3. Канал удален или не существует")
                
                # Пробуем получить по ссылке
                if TELEGRAM_CHANNEL.startswith('t.me/'):
                    try:
                        self.channel_entity = await self.client.get_entity(TELEGRAM_CHANNEL)
                        print(f"✅ Канал найден по ссылке: {self.channel_entity.title}")
                        return self.channel_entity
                    except:
                        pass
                
                return None
                
        except Exception as e:
            print(f"❌ Ошибка инициализации: {e}")
            return None

    async def parse_existing_posts(self, limit=1000):
        """Парсинг существующих постов в канале с проверкой дубликатов по содержанию"""
        print(f"🔄 Начинаем парсинг последних {limit} постов...")
        print(f"📋 Уже сохранено рецептов: {len(self.existing_recipes)}")
        
        recipes_found = 0
        duplicates_found = 0
        
        async for message in self.client.iter_messages(self.channel_entity, limit=limit):
            text = message.text or ""
            
            if message.media and hasattr(message.media, 'caption'):
                text += " " + (message.media.caption or "")
            
            if text and self.is_recipe_post(text):
                recipe_data = self.parse_recipe(text, message.id, message.date)
                if recipe_data:
                    if self.save_recipe(recipe_data):
                        recipes_found += 1
                        print(f"📖 Найден: {recipe_data['title']} (ID: {message.id})")
                    else:
                        duplicates_found += 1
        
        print(f"✅ Парсинг завершен!")
        print(f"📖 Найдено новых рецептов: {recipes_found}")
        print(f"🔄 Обнаружено дубликатов: {duplicates_found}")

    async def handle_new_message(self, event):
        """Обработка нового сообщения с проверкой дубликатов по содержанию"""
        try:
            message = event.message
            text = message.text or ""
            
            if message.media and hasattr(message.media, 'caption'):
                text += " " + (message.media.caption or "")
            
            if not text:
                return
                
            print(f"\n{'='*60}")
            print(f"📨 НОВОЕ СООБЩЕНИЕ!")
            print(f"📅 Дата: {message.date}")
            print(f"🆔 ID: {message.id}")
            print(f"📝 Длина текста: {len(text)} символов")
            print(f"📄 Превью: {text[:100]}...")
            
            if self.is_recipe_post(text):
                print("🎯 ОБНАРУЖЕН РЕЦЕПТ!")
                recipe_data = self.parse_recipe(text, message.id, message.date)
                
                if recipe_data:
                    if self.save_recipe(recipe_data):
                        print(f"📖 Название: {recipe_data['title']}")
                        print(f"🥕 Ингредиентов: {len(recipe_data['ingredients'])}")
                        print(f"👨‍🍳 Шагов: {len(recipe_data['steps'])}")
                        print(f"🏷️ Теги: {', '.join(recipe_data['tags'])}")
                    else:
                        print("⚠️ Рецепт уже существует (дубликат)")
                else:
                    print("❌ Не удалось распарсить рецепт")
            else:
                print("❌ Не рецепт, пропускаем")
                
            print(f"{'='*60}")
                
        except Exception as e:
            print(f"⚠️ Ошибка обработки сообщения: {e}")

    async def setup_event_handler(self):
        """Настройка обработчика событий (ИСПРАВЛЕННЫЙ СПОСОБ)"""
        print("\n🔧 Настройка обработчика новых сообщений...")
        
        # Способ 1: Используем декоратор внутри обработчика
        @self.client.on(events.NewMessage(chats=self.channel_entity))
        async def new_message_handler(event):
            await self.handle_new_message(event)
        
        print("✅ Обработчик событий настроен")
        
        # Способ 2: Альтернативный метод (раскомментируйте если первый не работает)
        # self.client.add_event_handler(
        #     self.handle_new_message,
        #     events.NewMessage(chats=self.channel_entity)
        # )

    async def run_monitoring(self):
        """Запуск мониторинга в реальном времени"""
        print(f"\n🟢 НАЧИНАЕМ МОНИТОРИНГ КАНАЛА: {self.channel_entity.title}")
        print("⏳ Ожидание новых сообщений...")
        print("⏹️  Для остановки нажмите Ctrl+C\n")
        
        # Запускаем бесконечный цикл прослушивания
        await self.client.run_until_disconnected()

    async def run(self, parse_existing=True):
        """Запуск парсера"""
        # Настраиваем канал
        channel = await self.setup_channel()
        if not channel:
            print("❌ Не удалось настроить канал")
            return

        # Парсинг существующих постов
        if parse_existing:
            await self.parse_existing_posts(limit=1000)

        # Настраиваем обработчик событий
        await self.setup_event_handler()

        # Загружаем статистику
        print(f"📊 Всего сохранено рецептов: {len(self.existing_recipes)}")
        
        # Получаем последний ID для проверки
        try:
            last_message = await self.client.get_messages(channel, limit=1)
            if last_message:
                print(f"📨 Последнее сообщение в канале: ID {last_message[0].id}")
        except:
            pass

        # Запускаем мониторинг
        await self.run_monitoring()

# Запуск с отладкой
if __name__ == "__main__":
    parser = TelegramRecipeParser()
    
    try:
        # Включаем подробное логирование
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        print("🚀 ЗАПУСК ПАРСЕРА ДЛЯ НЕ-АДМИНИСТРАТОРА")
        print("="*60)
        
        # Запускаем с парсингом истории
        asyncio.run(parser.run(parse_existing=True))
        
    except KeyboardInterrupt:
        print("\n🛑 Парсер остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()