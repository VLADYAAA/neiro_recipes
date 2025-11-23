import json
import re
import os
import requests
from typing import Dict, List, Any, Optional, Tuple
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import torch
import random
import time

logging.basicConfig(level=logging.ERROR)

class SmartRecipeBot:
    def __init__(self, recipes_file: str = "recipes.json", ollama_model: str = "mistral:7b-instruct"):
        self.recipes = self.load_recipes(recipes_file)
        self.last_search_results = []
        self.last_shown_recipe = None
        self.conversation_context = []
        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_model = ollama_model
        
        self.session_state = {
            'previous_recipes': [],
            'current_intent': None,
            'search_query': None,
            'waiting_for_selection': False,
            'current_page': 0,
            'all_search_results': []
        }

        print("🤖 Загружаю ML модели...")
        self.load_models()
        self.prepare_search_index()
        print("✅ Модели загружены!")

    def load_models(self):
        """Загружает ML модели"""
        try:
            self.model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
            print("✅ Загружена универсальная ML модель")
        except Exception as e:
            print(f"❌ Ошибка загрузки модели: {e}")
            self.model = None

    def call_ollama_model(self, prompt: str, max_tokens: int = 150, temperature: float = 0.3) -> str:
        """Вызов модели Ollama для анализа запросов"""
        try:
            data = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": 0.8,
                    "num_predict": max_tokens,
                    "stop": ["###", "Пользователь:", "User:"]
                }
            }
            
            response = requests.post(self.ollama_url, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json().get('response', '').strip()
                return result
            return ""
                
        except Exception as e:
            print(f"❌ Ошибка вызова Ollama: {e}")
            return ""

    def extract_keywords_with_ollama(self, query: str) -> Tuple[List[str], List[str]]:
        """Используем Ollama для выделения ключевых слов"""
        prompt = f"""Проанализируй кулинарный запрос и выдели ключевые слова для поиска рецептов.

Запрос: "{query}"

Ответь в формате:
БЛЮДА: слово1, слово2, слово3
ИНГРЕДИЕНТЫ: слово1, слово2, слово3

Правила:
- В БЛЮДАХ: названия конкретных блюд (пицца, борщ, салат, омлет)
- В ИНГРЕДИЕНТАХ: продукты и компоненты (курица, картошка, сыр, гречка)
- Только существительные, только кулинарные термины
- Игнорируй глаголы, прилагательные, местоимения

Примеры:
Запрос: "Найди рецепт греческой мусаки с курицей"
БЛЮДА: мусака
ИНГРЕДИЕНТЫ: курица, греческий

Запрос: "Хочу салат с помидорами и огурцами"
БЛЮДА: салат
ИНГРЕДИЕНТЫ: помидоры, огурцы

Запрос: "Что приготовить из картошки и грибов"
БЛЮДА: 
ИНГРЕДИЕНТЫ: картошка, грибы

Твой анализ:"""

        response = self.call_ollama_model(prompt, max_tokens=100, temperature=0.1)
        print(f"🧠 Анализ Ollama: {response}")
        
        # Парсим ответ
        dish_names = []
        ingredients = []
        
        # Ищем блюда
        dishes_match = re.search(r'БЛЮДА:\s*(.*?)(?:\n|$)', response)
        if dishes_match:
            dishes_text = dishes_match.group(1).strip()
            if dishes_text:
                dish_names = [d.strip().lower() for d in dishes_text.split(',') if d.strip()]
        
        # Ищем ингредиенты
        ingredients_match = re.search(r'ИНГРЕДИЕНТЫ:\s*(.*?)(?:\n|$)', response)
        if ingredients_match:
            ingredients_text = ingredients_match.group(1).strip()
            if ingredients_text:
                ingredients = [i.strip().lower() for i in ingredients_text.split(',') if i.strip()]
        
        # Fallback на старый метод если Ollama не сработал
        if not dish_names and not ingredients:
            return self.extract_search_terms_fallback(query)
        
        print(f"🔑 Ollama ключи - Блюда: {dish_names}, Ингредиенты: {ingredients}")
        return dish_names, ingredients

    def extract_search_terms_fallback(self, query: str) -> Tuple[List[str], List[str]]:
        """Fallback метод извлечения ключевых слов"""
        query_lower = query.lower()
        
        all_keywords = {
            'бургер', 'пицца', 'крем-брюле', 'оливье', 'борщ', 'цезарь', 'харчо',
            'шашлык', 'плов', 'паста', 'лазанья', 'суши', 'роллы', 'блины',
            'сырники', 'пельмени', 'вареники', 'оладьи', 'манник', 'печенье', 
            'кекс', 'бисквит', 'ганнаш', 'вафли', 'тосты', 'омлет', 'яичница', 
            'каша', 'творог', 'смузи', 'бутерброд', 'салат', 'суп', 'чипсы', 
            'рулет', 'котлеты', 'соус', 'мусака', 'греческая мусака',
            
            'курица', 'курка', 'куриц', 'куриную', 'куриной', 'куриный', 'грудка',
            'говядина', 'свинина', 'рыба', 'овощи', 'грибы', 'сыр', 'рис',
            'картофель', 'помидоры', 'лук', 'чеснок', 'перец', 'морковь',
            'яйца', 'молоко', 'сметана', 'творог', 'мука', 'сахар',
            'макароны', 'капуста', 'фасоль', 'горох', 'чечевица', 'яблоки',
            'шоколад', 'клубника', 'вишня', 'орехи', 'мед', 'кефир', 'йогурт',
            'сливки', 'масло', 'соль', 'перец',
            
            'гречка', 'гречневая', 'гречневая крупа', 'гречневая каша', 'греческий',
            'греческое', 'греческие'
        }
        
        found_keywords = []
        
        for keyword in all_keywords:
            if keyword in query_lower:
                found_keywords.append(keyword)
        
        if not found_keywords:
            words = re.findall(r'\b\w+\b', query_lower)
            for word in words:
                if len(word) > 3:
                    matching_keywords = [kw for kw in all_keywords if kw.startswith(word)]
                    if matching_keywords:
                        found_keywords.append(matching_keywords[0])
        
        # Разделяем на блюда и ингредиенты
        dish_names = [kw for kw in found_keywords if kw in [
            'бургер', 'пицца', 'крем-брюле', 'оливье', 'борщ', 'цезарь', 'харчо',
            'шашлык', 'плов', 'паста', 'лазанья', 'суши', 'роллы', 'блины',
            'сырники', 'пельмени', 'вареники', 'оладьи', 'манник', 'печенье', 
            'кекс', 'бисквит', 'ганнаш', 'вафли', 'тосты', 'омлет', 'яичница', 
            'каша', 'творог', 'смузи', 'бутерброд', 'салат', 'суп', 'чипсы', 
            'рулет', 'котлеты', 'соус', 'мусака', 'греческая мусака'
        ]]
        
        ingredients = [kw for kw in found_keywords if kw not in dish_names]
        
        return dish_names, ingredients

    def prepare_search_index(self):
        """Подготавливает поисковый индекс"""
        print("📊 Подготавливаю поисковый индекс...")

        self.search_texts = []
        self.recipe_indices = []
        self.recipe_titles = []

        for i, recipe in enumerate(self.recipes):
            title = recipe.get('title', '').lower()
            tags = ' '.join(recipe.get('tags', [])).lower()
            ingredients = ' '.join([str(ing).lower() for ing in recipe.get('ingredients', [])])
            description = recipe.get('description', '').lower()
            
            search_text = f"{title} {title} {title} {ingredients} {tags} {description}"
            
            self.search_texts.append(search_text)
            self.recipe_indices.append(i)
            self.recipe_titles.append(title)

        if self.model:
            try:
                self.recipe_embeddings = self.model.encode(self.search_texts)
                self.prepare_intent_embeddings()
                print("✅ Все эмбеддинги созданы")
            except Exception as e:
                print(f"❌ Ошибка создания эмбеддингов: {e}")

    def prepare_intent_embeddings(self):
        """Подготавливает эмбеддинги для классификации намерений"""
        self.intent_examples = {
            "точный_поиск": [
                "рецепт пиццы", "как приготовить борщ", "хочу бургер", 
                "найди крем-брюле", "рецепт куриной грудки", "шашлык",
                "приготовь пасту", "рецепт оливье", "суп харчо",
                "покажи рецепт блинов", "оладьи на кефире", "вафли",
                "гречка", "сырники", "омлет", "яичница", "куринная грудка",
                "куриная грудка", "куриные котлеты", "мусака", "греческая мусака",
                "гречневая крупа", "гречневая каша"
            ],
            "общий_поиск": [
                "что приготовить с курицей", "рецепты с рисом", "блюда из мяса",
                "что сделать с овощами", "идеи с грибами", "рецепты для ужина",
                "что можно приготовить из картофеля", "блюда с сыром",
                "рецепты с яйцами", "что приготовить на завтрак",
                "хочу что-то с шоколадом", "что-то с рыбой", "что-то с гречкой",
                "найди что-нибудь с шоколадом", "рецепты с курицей", "завтрак",
                "что приготовить на завтрак", "идеи для завтрака",
                "быстрый завтрак", "утренние рецепты", "рецепты для завтрака",
                "я хочу приготовить куринную грудку", "приготовь мне курицу",
                "найди что то с гречкой", "рецепт с гречневой крупой",
                "хочу что-то греческое"
            ],
            "рекомендация": [
                "посоветуй что-нибудь", "что приготовить", "выбери рецепт",
                "удиви меня", "не знаю что готовить", "давай что-нибудь вкусное",
                "порекомендуй блюдо", "хочу попробовать что-то новое",
                "какой рецепт посоветуешь", "что сегодня приготовить"
            ],
            "смена_темы": [
                "другой вариант", "еще рецепт", "следующий", "покажи другой",
                "не это", "давай что-то другое", "еще вариант", "другой",
                "следующее блюдо", "попробуем другой рецепт", "хочу другой список",
                "покажи еще", "дальше", "следующая страница", "еще"
            ],
            "приветствие": [
                "привет", "здравствуйте", "добрый день", "доброе утро",
                "добрый вечер", "хай", "приветик", "начать", "старт"
            ],
            "прощание": [
                "пока", "до свидания", "выход", "спокойной ночи",
                "всего доброго", "пока пока", "до встречи", "закончить"
            ],
            "общение": [
                "как дела", "как ты", "что нового", "как жизнь",
                "что делаешь", "расскажи о себе", "ты кто", "что ты умеешь"
            ],
            "благодарность": [
                "спасибо", "благодарю", "отлично", "супер", "класс"
            ]
        }

        self.intent_embeddings = {}
        for intent, examples in self.intent_examples.items():
            self.intent_embeddings[intent] = self.model.encode(examples)

    def load_recipes(self, file_path: str) -> List[Dict[str, Any]]:
        """Загружает рецепты из JSON файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    print(f"✅ Загружено {len(data)} рецептов")
                    return data
                else:
                    return [data]
        except Exception as e:
            print(f"❌ Ошибка загрузки: {e}")
            return []

    def classify_intent_ml(self, message: str) -> str:
        """Классифицирует намерение через ML"""
        if not self.model:
            return "общий_поиск"

        try:
            message_embedding = self.model.encode([message])[0]
            max_similarity = 0
            detected_intent = "общий_поиск"

            for intent, intent_embeddings in self.intent_embeddings.items():
                similarities = cosine_similarity([message_embedding], intent_embeddings)[0]
                avg_similarity = np.mean(similarities)
                
                if avg_similarity > max_similarity and avg_similarity > 0.5:
                    max_similarity = avg_similarity
                    detected_intent = intent

            self.session_state['current_intent'] = detected_intent
            return detected_intent

        except Exception as e:
            print(f"⚠️ Ошибка ML классификации: {e}")
            return "общий_поиск"

    def recipe_matches_search(self, recipe: Dict[str, Any], dish_names: List[str], ingredients: List[str]) -> Tuple[bool, int, int]:
        """Проверяет, соответствует ли рецепт поисковому запросу, возвращает (совпадение, счетчик блюд, счетчик ингредиентов)"""
        if not dish_names and not ingredients:
            return True, 0, 0
            
        recipe_text = f"{recipe.get('title', '').lower()} {' '.join([str(ing).lower() for ing in recipe.get('ingredients', [])])} {' '.join(recipe.get('tags', []))}"
        
        dish_match_count = 0
        ingredient_match_count = 0
        
        # Проверяем названия блюд
        if dish_names:
            for dish in dish_names:
                if dish in recipe_text:
                    dish_match_count += 1
        
        # Проверяем ингредиенты - если больше 2 ингредиентов, требуем чтобы все были в рецепте
        if ingredients:
            if len(ingredients) >= 2:
                # Для 3+ ингредиентов требуем полное совпадение всех
                all_ingredients_present = True
                for ingredient in ingredients:
                    if ingredient not in recipe_text:
                        all_ingredients_present = False
                        break
                if all_ingredients_present:
                    ingredient_match_count = len(ingredients)
            else:
                # Для 1-2 ингредиентов считаем частичные совпадения
                for ingredient in ingredients:
                    if ingredient in recipe_text:
                        ingredient_match_count += 1
        
        # Рецепт подходит если:
        # - Есть совпадения по блюдам ИЛИ
        # - Есть совпадения по ингредиентам (для 3+ ингредиентов - все должны совпасть)
        matches = (dish_match_count > 0) or (ingredient_match_count > 0)
        
        return matches, dish_match_count, ingredient_match_count

    def enhanced_semantic_search(self, query: str, dish_names: List[str], ingredients: List[str]) -> List[Tuple[Dict[str, Any], float]]:
        """Улучшенный семантический поиск с правильной сортировкой"""
        if not self.model:
            return []

        try:
            query_embedding = self.model.encode([query])[0]
            similarities = cosine_similarity([query_embedding], self.recipe_embeddings)[0]

            results = []
            
            # Сначала собираем все потенциальные результаты
            for idx, similarity in enumerate(similarities):
                recipe = self.recipes[idx]
                
                # Проверяем соответствие поисковым терминам
                matches, dish_count, ingredient_count = self.recipe_matches_search(recipe, dish_names, ingredients)
                
                if not matches:
                    continue
                
                # Базовый score
                base_score = similarity
                
                # Усиление за точные совпадения в названии
                title_boost = 0
                recipe_title = recipe.get('title', '').lower()
                for dish in dish_names:
                    if dish in recipe_title:
                        title_boost += 0.4
                
                # Усиление за ингредиенты
                ingredient_boost = ingredient_count * 0.2
                
                final_score = min(base_score + title_boost + ingredient_boost, 1.0)
                
                if final_score > 0.3:
                    results.append((recipe, final_score, dish_count, ingredient_count))

            # Сортируем результаты по приоритету:
            # 1. Сначала рецепты с совпадениями по названию блюд
            # 2. Затем по количеству совпавших ингредиентов
            # 3. Затем по семантической схожести
            results.sort(key=lambda x: (x[2] > 0, x[3], x[1]), reverse=True)
            
            # Убираем дубликаты и возвращаем только рецепты и scores
            seen_titles = set()
            unique_results = []
            for recipe, score, dish_count, ingredient_count in results:
                title = recipe.get('title', '')
                if title not in seen_titles:
                    seen_titles.add(title)
                    unique_results.append((recipe, score))

            return unique_results

        except Exception as e:
            print(f"⚠️ Ошибка семантического поиска: {e}")
            return []

    def smart_search(self, query: str) -> List[Tuple[Dict[str, Any], float]]:
        """Умный поиск рецептов с использованием Ollama для анализа"""
        print(f"🔍 Анализирую запрос: '{query}'")

        intent = self.classify_intent_ml(query)
        print(f"🎯 Намерение: {intent}")

        # Используем Ollama для выделения ключевых слов
        dish_names, ingredients = self.extract_keywords_with_ollama(query)
        print(f"🔑 Ключевые слова - Блюда: {dish_names}, Ингредиенты: {ingredients}")

        self.session_state['search_query'] = query
        self.session_state['waiting_for_selection'] = False

        # Обработка смены темы
        if intent == "смена_темы" and self.session_state['all_search_results']:
            self.session_state['current_page'] += 1
            current_page = self.session_state['current_page']
            all_results = self.session_state['all_search_results']
            
            start_idx = current_page * 5
            end_idx = start_idx + 5
            
            if start_idx < len(all_results):
                page_results = all_results[start_idx:end_idx]
                print(f"📄 Показываю страницу {current_page + 1}")
                return page_results
            else:
                print("📄 Больше нет результатов")
                return []

        # Новый поиск
        results = self.enhanced_semantic_search(query, dish_names, ingredients)
        
        # Сохраняем все результаты для пагинации
        self.session_state['all_search_results'] = results
        self.session_state['current_page'] = 0

        print(f"🎯 Найдено {len(results)} рецептов")
        return results[:5] if results else []

    def generate_ollama_response(self, intent: str, query: str) -> str:
        """Генерирует ответ с помощью Ollama для общения"""
        if intent == "приветствие":
            prompt = """Пользователь поздоровался. Ответь кратко и дружелюбно, представься как кулинарный помощник и предложи помощь с рецептами.

Ответ (1-2 предложения):"""
        
        elif intent == "общение":
            prompt = f"""Пользователь: "{query}"
            
Ты - кулинарный помощник. Ответь кратко и вежливо, верни разговор к теме рецептов.

Ответ (1-2 предложения):"""
        
        elif intent == "благодарность":
            prompt = f"""Пользователь поблагодарил: "{query}"
            
Ответь кратко и вежливо, предложи дальнейшую помощь.

Ответ (1 предложение):"""
        
        else:
            return ""

        response = self.call_ollama_model(prompt, max_tokens=80, temperature=0.7)
        return response.strip()

    def generate_response(self, intent: str, query: str, found_recipes: List[Tuple[Dict[str, Any], float]]) -> str:
        """Генерирует ответ"""
        self.last_search_results = found_recipes

        # Используем Ollama для генерации ответов при общении
        if intent in ["приветствие", "общение", "благодарность"]:
            ollama_response = self.generate_ollama_response(intent, query)
            if ollama_response:
                return ollama_response

        if intent == "прощание":
            return "До свидания! Надеюсь, нашли что-то вкусное! 🍽️"

        elif intent == "рекомендация":
            if not found_recipes:
                available_recipes = [r for r in self.recipes if r.get('title') not in self.session_state['previous_recipes']]
                random_recipes = random.sample(available_recipes, min(5, len(available_recipes)))
                self.last_search_results = [(r, 0.8) for r in random_recipes]
                return "Вот несколько случайных рецептов:"

        elif intent == "смена_темы":
            if not found_recipes:
                return "Больше нет рецептов для показа. Попробуйте новый поиск."

        if not found_recipes:
            dish_names, ingredients = self.extract_keywords_with_ollama(query)
            if dish_names or ingredients:
                return f"К сожалению, не нашла рецептов с {', '.join(dish_names + ingredients)}. Попробуйте уточнить запрос."
            else:
                return "Извините, не поняла ваш запрос. Попробуйте ввести название блюда или ингредиенты."

        if len(found_recipes) == 1 and found_recipes[0][1] > 0.8:
            recipe, score = found_recipes[0]
            self.last_shown_recipe = recipe.get('title')
            self.session_state['previous_recipes'].append(recipe.get('title'))
            return "🎯 Отлично! Нашла для вас идеальный рецепт:"
        else:
            total_results = len(self.session_state['all_search_results'])
            current_page = self.session_state['current_page']
            shown_count = len(found_recipes)
            start_idx = current_page * 5 + 1
            end_idx = start_idx + shown_count - 1
            
            return f"🍽️ Нашла {total_results} рецептов (показано {start_idx}-{end_idx}):"

    def format_recipe_response(self, recipe: Dict[str, Any]) -> str:
        """Форматирует полный рецепт"""
        response = f"\n\n### 🍳 {recipe.get('title', 'Рецепт')}\n"
        response += "-" * 40 + "\n"

        if recipe.get('description'):
            response += f"{recipe['description']}\n\n"

        if recipe.get('temperature'):
            response += f"🌡️ Температура: {recipe['temperature']}\n"
        if recipe.get('time'):
            response += f"⏰ Время: {recipe['time']}\n"

        if recipe.get('ingredients'):
            response += "\n📦 **Ингредиенты:**\n"
            for ingredient in recipe['ingredients']:
                response += f"  - {ingredient}\n"

        if recipe.get('steps'):
            response += "\n📝 **Приготовление:**\n"
            for i, step in enumerate(recipe['steps'], 1):
                clean_step = re.sub(r'[▪️️♨️🔥]', '', step).strip()
                if clean_step:
                    response += f"  {i}. {clean_step}\n"

        if recipe.get('tags'):
            response += f"\n🏷️ **Категории:** {', '.join(recipe['tags'])}\n"

        response += "\n" + "-" * 40
        return response

    def format_recipe_list(self, recipes: List[Tuple[Dict[str, Any], float]]) -> str:
        """Форматирует список рецептов с инструкцией отказа"""
        if not recipes:
            return ""

        if len(recipes) == 1 and recipes[0][1] > 0.8:
            recipe, score = recipes[0]
            self.last_shown_recipe = recipe.get('title')
            self.session_state['previous_recipes'].append(recipe.get('title'))
            return self.format_recipe_response(recipe)

        recipes_to_show = recipes
        self.session_state['waiting_for_selection'] = True

        response = []
        for i, (recipe, score) in enumerate(recipes_to_show, 1):
            title = recipe.get('title', 'Рецепт без названия')
            time_info = f" (⏰ {recipe['time']})" if recipe.get('time') else ""
            tags_info = f" [🏷️ {', '.join(recipe['tags'])}]" if recipe.get('tags') else ""
            response.append(f"{i}. **{title}**{time_info}{tags_info}")

        total_results = len(self.session_state['all_search_results'])
        current_page = self.session_state['current_page']
        
        pagination_info = f"\n\n📄 Страница {current_page + 1} из {((total_results - 1) // 5) + 1}"
        
        # ВАЖНО: Инструкция для отказа от выбора
        navigation_info = "\n\n*Выберите номер рецепта 📋 или скажите 'другой рецепт' 🔄 для нового поиска*"
        
        return "\n" + "\n".join(response) + pagination_info + navigation_info

    def is_selection_from_list(self, message: str) -> bool:
        """Проверяет, является ли сообщение выбором из списка"""
        if not self.last_search_results or not self.session_state['waiting_for_selection']:
            return False
        
        # Проверяем отказ от выбора
        if message.lower() in ['другой рецепт', 'другой', 'новый поиск', 'еще', 'дальше']:
            return True
            
        if message.isdigit():
            number = int(message)
            return 1 <= number <= len(self.last_search_results)
            
        message_lower = message.lower()
        for recipe, score in self.last_search_results:
            title = recipe.get('title', '').lower()
            if (message_lower in title or 
                any(word in title for word in message_lower.split())):
                return True
                
        return False

    def select_recipe(self, selection: str) -> Optional[Dict[str, Any]]:
        """Выбирает рецепт по номеру или названию (БЕЗ нейросети)"""
        if not self.last_search_results:
            return None

        # Обработка отказа от выбора
        if selection.lower() in ['другой рецепт', 'другой', 'новый поиск', 'еще', 'дальше']:
            self.session_state['waiting_for_selection'] = False
            self.session_state['all_search_results'] = []
            self.last_search_results = []
            return None  # Специальное значение для отказа

        # Выбор по номеру (БЕЗ нейросети)
        if selection.isdigit():
            number = int(selection)
            if 1 <= number <= len(self.last_search_results):
                recipe, score = self.last_search_results[number - 1]
                self.session_state['previous_recipes'].append(recipe.get('title'))
                self.session_state['waiting_for_selection'] = False
                return recipe

        # Выбор по названию (БЕЗ нейросети - простое сравнение строк)
        selection_lower = selection.lower()
        for recipe, score in self.last_search_results:
            title = recipe.get('title', '').lower()
            if (selection_lower in title or 
                any(word in title for word in selection_lower.split())):
                self.session_state['previous_recipes'].append(recipe.get('title'))
                self.session_state['waiting_for_selection'] = False
                return recipe

        return None

    def process_message(self, message: str) -> str:
        """Обрабатывает сообщение пользователя"""
        if not message.strip():
            return "Пожалуйста, опишите, что вы хотите приготовить."

        # ШАГ 4: Обработка выбора из списка (БЕЗ нейросети)
        if self.session_state['waiting_for_selection'] and self.is_selection_from_list(message):
            selected_recipe = self.select_recipe(message)
            
            # Пользователь отказался от выбора
            if selected_recipe is None and message.lower() in ['другой рецепт', 'другой', 'новый поиск']:
                self.session_state['waiting_for_selection'] = False
                self.session_state['all_search_results'] = []
                return "Хорошо! Что бы вы хотели приготовить вместо этого? 🍳"
            
            # Пользователь выбрал рецепт
            if selected_recipe:
                self.last_shown_recipe = selected_recipe.get('title')
                return self.format_recipe_response(selected_recipe)
            else:
                return "Рецепт не найден. Выберите номер или название из списка, или скажите 'другой рецепт'."

        # ШАГ 1-3: Анализ запроса и поиск (С нейросетью)
        intent = self.classify_intent_ml(message)

        if intent in ["приветствие", "прощание", "общение", "благодарность"]:
            return self.generate_response(intent, message, [])

        # Используем нейросеть для анализа поискового запроса
        recipes = self.smart_search(message)

        main_response = self.generate_response(intent, message, recipes)
        recipes_formatted = self.format_recipe_list(recipes)

        return f"{main_response}{recipes_formatted}"

    def run_chat(self):
        """Запускает интерактивный чат"""
        print("\n" + "=" * 70)
        print("🤖 УМНЫЙ ПОМОЩНИК РЕЦЕПТОВ С PURE ML + OLLAMA")
        print("=" * 70)
        print(f"📁 Загружено рецептов: {len(self.recipes)}")
        print(f"🧠 Использую ML + Ollama модель: {self.ollama_model}")
        print("🎯 Умный анализ запросов и поиск по рецептам")
        print("\nПримеры:")
        print("• 'Греческая мусака' - поиск по названию")
        print("• 'Рецепт с гречкой и курицей' - поиск по ингредиентам") 
        print("• 'Покажи еще' - следующая страница")
        print("• '1' или 'название' - выбор рецепта")
        print("=" * 70)

        while True:
            try:
                user_input = input("\n👤 Вы: ").strip()

                if user_input.lower() in ['пока', 'выход', 'до свидания', 'закончить']:
                    print(f"\n🤖 Бот: {self.generate_response('прощание', user_input, [])}")
                    break

                response = self.process_message(user_input)
                print(f"\n🤖 Бот: {response}")

            except KeyboardInterrupt:
                print(f"\n🤖 Бот: {self.generate_response('прощание', 'пока', [])}")
                break
            except Exception as e:
                print(f"\n🤖 Бот: Извините, произошла ошибка. Попробуйте еще раз.")
                logging.error(f"Error: {e}")

if __name__ == "__main__":
    # Проверяем доступные модели Ollama
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=30)
        models = [model['name'] for model in response.json().get('models', [])]
        print("Доступные модели Ollama:", models)
        
        selected_model = "llama3.2:3b"
        
        print(f"Используем модель: {selected_model}")
        bot = SmartRecipeBot("recipes.json", selected_model)
        
    except Exception as e:
        print(f"❌ Ошибка подключения к Ollama: {e}")
        print("Запустите Ollama: ollama serve")
        exit(1)
        
    bot.run_chat()