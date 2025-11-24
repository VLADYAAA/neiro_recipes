from flask import Flask, request, jsonify
import logging
from be1 import SmartRecipeBot
import ssl

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = SmartRecipeBot("recipes.json")

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

def create_alice_response(text, tts=None, buttons=None, end_session=False):
    """Создает ответ для Яндекс Алисы"""
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
    
    return response

@app.route('/')
def index():
    return "Кулинарный помощник для Яндекс Алисы работает!"

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
        
        # Обрабатываем начало сессии
        if request_data.get('type') == 'SimpleUtterance' and 'марку' in request_data.get('command', '').lower():
            return jsonify(create_alice_response(
                "Это кулинарный помощник! " + START_MESSAGE,
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Блюда с курицей", "hide": True},
                    {"title": "Десерты", "hide": True}
                ]
            ))
        
        # Новый сеанс или команда "Помощь"
        if (session.get('new') or 
            request_data.get('command', '').lower() in ['помощь', 'что ты умеешь', 'help']):
            return jsonify(create_alice_response(
                START_MESSAGE,
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Блюда с курицей", "hide": True},
                    {"title": "Десерты", "hide": True}
                ]
            ))
        
        # Выход
        if request_data.get('command', '').lower() in ['пока', 'выход', 'закончить']:
            return jsonify(create_alice_response("До свидания! Приятного аппетита!", end_session=True))
        
        # Обрабатываем команду пользователя
        user_message = request_data.get('command', '').strip()
        
        if not user_message:
            return jsonify(create_alice_response(
                "Что вы хотите приготовить?",
                buttons=[
                    {"title": "Найди рецепт пиццы", "hide": True},
                    {"title": "Блюда с курицей", "hide": True},
                    {"title": "Помощь", "hide": True}
                ]
            ))
        
        # Обрабатываем сообщение через бота
        bot_response = bot.process_message(user_message)
        
        # Создаем кнопки для навигации
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
                {"title": "Другой рецепт", "hide": True}
            ])
        else:
            # Обычное состояние
            buttons.extend([
                {"title": "Найди рецепт пиццы", "hide": True},
                {"title": "Блюда с курицей", "hide": True},
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
            port=8443,
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