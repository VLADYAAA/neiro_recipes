from flask import Flask, request, jsonify
import logging
from be1 import SmartRecipeBot
import ssl
import json
import re
import os
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class AutoReloadRecipeBot:
    def __init__(self, recipe_file):
        self.recipe_file = recipe_file
        self.bot = None
        self.last_modified = 0
        self.load_recipes()
    
    def load_recipes(self):
        """Загружает или перезагружает рецепты если файл изменился"""
        try:
            if os.path.exists(self.recipe_file):
                current_modified = os.path.getmtime(self.recipe_file)
                if current_modified > self.last_modified or self.bot is None:
                    self.bot = SmartRecipeBot(self.recipe_file)
                    self.last_modified = current_modified
                    logger.info("Recipes loaded/reloaded successfully")
                    return True
            else:
                logger.error(f"Recipe file {self.recipe_file} not found")
        except Exception as e:
            logger.error(f"Error loading recipes: {e}")
        return False
    
    def process_message(self, message):
        """Проверяет актуальность данных перед обработкой"""
        self.load_recipes()
        if self.bot:
            return self.bot.process_message(message)
        else:
            return "Извините, не удалось загрузить рецепты. Проверьте файл с рецептами."

# Инициализируем бота с автоперезагрузкой
bot = AutoReloadRecipeBot("recipes.json")

# Временное хранилище для частей рецептов (в памяти)
recipe_parts_store = {}

# Стартовое сообщение с инструкцией
START_MESSAGE = """Привет! Я ваш кулинарный помощник. 

Для поиска рецептов используйте команды:
• "Найди рецепт пиццы"
• "Найди блюда с курицей и картошкой" 

При выборе из списка можно сказать:
• "Первое", "Второе", "Третье"
• "Покажи еще" - следующая страница
• "Другой рецепт" - новый поиск

Что хотите приготовить?"""

def split_by_sentences(text, max_length=1000):
    """Разбивает текст на части по предложениям, не превышая max_length"""
    if len(text) <= max_length:
        return [text]
    
    # Разделяем текст на предложения, но игнорируем точки после цифр (например, "1.")
    # Используем негативный просмотр назад, чтобы исключить цифры перед точкой
    sentences = re.split(r'(?<!\d)\.\s+(?=[А-ЯA-Z])|\!\s+|\?\s+', text)
    
    parts = []
    current_part = ""
    
    for sentence in sentences:
        # Восстанавливаем знак препинания в конце предложения
        # Находим какой знак был использован для разделения
        if current_part:
            # Добавляем точку к предыдущему предложению (кроме первого)
            current_part += "."
        
        # Если добавление следующего предложения не превысит лимит
        if len(current_part) + len(sentence) + 1 <= max_length:
            if current_part:
                current_part += " " + sentence
            else:
                current_part = sentence
        else:
            # Если текущая часть не пустая, сохраняем ее
            if current_part:
                parts.append(current_part.strip())
            
            # Если одно предложение само по себе длиннее max_length,
            # разбиваем его по словам
            if len(sentence) > max_length:
                words = sentence.split()
                current_part = ""
                for word in words:
                    if len(current_part) + len(word) + 1 <= max_length:
                        if current_part:
                            current_part += " " + word
                        else:
                            current_part = word
                    else:
                        if current_part:
                            parts.append(current_part.strip())
                        current_part = word
            else:
                current_part = sentence
    
    # Добавляем последнюю часть
    if current_part:
        parts.append(current_part.strip())
    
    return parts

def split_long_response(text):
    """Разбивает длинный текст на части по предложениям"""
    if len(text) <= 1024:
        return [text]
    
    # Сначала пробуем разбить по предложениям
    parts = split_by_sentences(text, 1000)
    
    # Если все равно есть слишком длинные части, разбиваем принудительно
    final_parts = []
    for part in parts:
        if len(part) > 1024:
            # Принудительно разбиваем на части по 1000 символов, но стараясь по словам
            words = part.split()
            current_chunk = ""
            for word in words:
                if len(current_chunk) + len(word) + 1 <= 1000:
                    if current_chunk:
                        current_chunk += " " + word
                    else:
                        current_chunk = word
                else:
                    if current_chunk:
                        final_parts.append(current_chunk.strip())
                    current_chunk = word
            if current_chunk:
                final_parts.append(current_chunk.strip())
        else:
            final_parts.append(part)
    
    return final_parts

def create_alice_response(text, tts=None, buttons=None, end_session=False, session_state=None):
    """Создает ответ для Яндекс Алисы с гарантированной длиной до 1024 символов"""
    # ГАРАНТИРУЕМ что текст не превышает 1024 символа
    text = text[:1024]
    
    response = {
        "response": {
            "text": text,
            "end_session": end_session
        },
        "version": "1.0"
    }
    
    if tts:
        response["response"]["tts"] = tts
    
    if buttons:
        response["response"]["buttons"] = buttons
    
    if session_state:
        response["session_state"] = session_state
    
    return response

@app.route('/')
def index():
    return "Кулинарный помощник для Яндекс Алисы работает!"

@app.route('/reload-recipes', methods=['POST'])
def reload_recipes():
    """Принудительная перезагрузка рецептов"""
    try:
        if bot.load_recipes():
            return jsonify({"status": "success", "message": "Recipes reloaded successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to reload recipes"}), 500
    except Exception as e:
        logger.error(f"Error reloading recipes: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        logger.info(f"Received data: {data}")
        
        # Проверяем, что это запрос от Алисы
        if not data or 'request' not in data:
            return jsonify(create_alice_response("Произошла ошибка", end_session=True))
        
        request_data = data['request']
        session = data.get('session', {})
        session_id = session.get('session_id', 'default')
        
        # Получаем состояние сессии
        state = data.get('state', {})
        session_state = state.get('session', {}) if state else {}
        
        logger.info(f"Session ID: {session_id}")
        
        # Обрабатываем начало сессии
        if request_data.get('type') == 'SimpleUtterance' and 'марку' in request_data.get('command', '').lower():
            return jsonify(create_alice_response(
                "Это кулинарный помощник! " + START_MESSAGE,
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Найди десерты", "hide": True}
                ]
            ))
        
        # Новый сеанс или команда "Помощь"
        if (session.get('new') or 
            request_data.get('command', '').lower() in ['помощь', 'что ты умеешь', 'help']):
            # Очищаем сохраненные части при новом сеансе
            if session_id in recipe_parts_store:
                del recipe_parts_store[session_id]
                
            return jsonify(create_alice_response(
                START_MESSAGE,
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Найди десерты", "hide": True}
                ]
            ))
        
        # Выход
        if request_data.get('command', '').lower() in ['пока', 'выход', 'закончить']:
            # Очищаем сохраненные части при выходе
            if session_id in recipe_parts_store:
                del recipe_parts_store[session_id]
            return jsonify(create_alice_response("До свидания! Приятного аппетита!", end_session=True))
        
        # Обрабатываем команду пользователя
        user_message = request_data.get('command', '').strip()
        
        if not user_message:
            return jsonify(create_alice_response(
                "Что вы хотите приготовить?",
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Найди помощь", "hide": True}
                ]
            ))
        
        user_message_lower = user_message.lower()
        
        # Обрабатываем команду "другой рецепт" - сбрасываем состояние
        if user_message_lower in ['другой рецепт', 'новый поиск', 'сброс']:
            # Очищаем сохраненные части
            if session_id in recipe_parts_store:
                del recipe_parts_store[session_id]
            
            return jsonify(create_alice_response(
                "Хорошо, начинаем новый поиск. Что вы хотите приготовить?",
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Помощь", "hide": True}
                ]
            ))
        
        # Обрабатываем команду "далее" для продолжения чтения рецепта
        if user_message_lower in ['далее', 'продолжи', 'следующая часть']:
            logger.info(f"Processing 'next' command for session: {session_id}")
            
            # Проверяем есть ли сохраненные части для этой сессии
            if session_id in recipe_parts_store and recipe_parts_store[session_id]:
                remaining_parts = recipe_parts_store[session_id]
                logger.info(f"Found {len(remaining_parts)} remaining parts")
                
                if remaining_parts:
                    next_part = remaining_parts[0]
                    new_remaining_parts = remaining_parts[1:]
                    
                    # Обновляем хранилище
                    recipe_parts_store[session_id] = new_remaining_parts
                    
                    # Добавляем подсказку для продолжения, если есть еще части
                    if new_remaining_parts:
                        # Обрезаем часть и добавляем короткое сообщение
                        if len(next_part) > 1000:
                            next_part = next_part[:1000]
                        next_part += "\n\n(Скажите 'далее' для продолжения)"
                        buttons = [
                            {"title": "Далее", "hide": True},
                            {"title": "Другой рецепт", "hide": True},
                            {"title": "Помощь", "hide": True}
                        ]
                    else:
                        # Последняя часть
                        if len(next_part) > 1000:
                            next_part = next_part[:1000]
                        next_part += "\n\nПриятного аппетита"
                        buttons = [
                            {"title": "Другой рецепт", "hide": True},
                            {"title": "Помощь", "hide": True}
                        ]
                    
                    logger.info(f"Sending part, remaining: {len(new_remaining_parts)}")
                    
                    return jsonify(create_alice_response(
                        next_part,
                        buttons=buttons
                    ))
            
            # Если частей нет
            return jsonify(create_alice_response(
                "Больше нет частей для продолжения. Начните новый поиск.",
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Помощь", "hide": True}
                ]
            ))
        
        # Обрабатываем команду "покажи еще" для пагинации
        if user_message_lower in ['покажи еще', 'еще', 'дальше', 'следующие']:
            # Используем специальную команду для пагинации
            bot_response = bot.process_message("покажи еще")
            
            # ВАЖНО: Проверяем длину ответа даже для пагинации
            if len(bot_response) > 1024:
                parts = split_long_response(bot_response)
                if len(parts) > 1:
                    first_part = parts[0]
                    remaining_parts = parts[1:]
                    recipe_parts_store[session_id] = remaining_parts
                    
                    # Обрезаем и добавляем короткое сообщение
                    if len(first_part) > 1000:
                        first_part = first_part[:1000]
                    first_part += "\n\n(Скажите 'далее' для продолжения)"
                    
                    return jsonify(create_alice_response(
                        first_part,
                        buttons=[
                            {"title": "Далее", "hide": True},
                            {"title": "Другой рецепт", "hide": True}
                        ]
                    ))
            
            buttons = []
            if "Нашла" in bot_response and "рецептов" in bot_response:
                buttons.extend([
                    {"title": "Покажи еще", "hide": True},
                    {"title": "Другой рецепт", "hide": True}
                ])
            elif "Укажите номер рецепта" in bot_response:
                buttons.extend([
                    {"title": "Первое", "hide": True},
                    {"title": "Второе", "hide": True},
                    {"title": "Другой рецепт", "hide": True}
                ])
            else:
                buttons.extend([
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Найди блюда с курицей", "hide": True},
                    {"title": "Помощь", "hide": True}
                ])
            
            return jsonify(create_alice_response(
                bot_response,
                buttons=buttons
            ))
        
        # Обрабатываем сообщение через бота
        bot_response = bot.process_message(user_message)
        logger.info(f"Bot response length: {len(bot_response)}")
        
        # ВАЖНО: Проверяем длину ВСЕХ ответов от бота, включая выбор рецепта по номеру
        if len(bot_response) > 1024:
            parts = split_long_response(bot_response)
            logger.info(f"Split into {len(parts)} parts")
            
            # Если ответ разбит на части, отправляем первую часть
            # и сохраняем остальные в нашем хранилище
            if len(parts) > 1:
                first_part = parts[0]
                remaining_parts = parts[1:]
                
                # Сохраняем оставшиеся части в хранилище
                recipe_parts_store[session_id] = remaining_parts
                
                # Обрезаем первую часть и добавляем подсказку
                if len(first_part) > 1000:
                    first_part = first_part[:1000]
                first_part += "\n\n(Скажите 'далее' для продолжения)"
                
                buttons = [
                    {"title": "Далее", "hide": True},
                    {"title": "Другой рецепт", "hide": True},
                    {"title": "Помощь", "hide": True}
                ]
                
                logger.info(f"Saving {len(remaining_parts)} remaining parts for session: {session_id}")
                
                return jsonify(create_alice_response(
                    first_part,
                    buttons=buttons
                ))
        
        # Обычная обработка для коротких ответов
        buttons = []
        if "Нашла" in bot_response and "рецептов" in bot_response:
            # Если показан список рецептов
            buttons.extend([
                {"title": "Покажи еще", "hide": True},
                {"title": "Другой рецепт", "hide": True}
            ])
        elif "Укажите номер рецепта" in bot_response:
            # Если нужно выбрать из списка
            buttons.extend([
                {"title": "Первое", "hide": True},
                {"title": "Второе", "hide": True},
                {"title": "Третье", "hide": True},
                {"title": "Другой рецепт", "hide": True}
            ])
        else:
            # Обычное состояние (полный рецепт или другой ответ)
            buttons.extend([
                {"title": "Другой рецепт", "hide": True},
                {"title": "Помощь", "hide": True}
            ])
        
        return jsonify(create_alice_response(
            bot_response,
            buttons=buttons
        ))
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return jsonify(create_alice_response(
            "Извините, произошла ошибка. Попробуйте еще раз.",
            end_session=True
        ))

if __name__ == '__main__':
    # Запуск с SSL для HTTPS
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    
    # Укажите пути к вашим сертификатам
    try:
        context.load_cert_chain('cert.pem', 'key.pem')
        logger.info("SSL certificates loaded successfully")
        
        app.run(
            host='0.0.0.0',
            port=5000,
            ssl_context=context,
            debug=False
        )
    except FileNotFoundError:
        logger.warning("SSL certificates not found, running without HTTPS")
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False
        )