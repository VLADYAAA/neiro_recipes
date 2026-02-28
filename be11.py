import json
import re
import os
from typing import Dict, List, Any, Optional, Tuple
import logging
import random
NUMBER_WORDS = {
    'первое': 1, 'первый': 1, 'первую': 1, 'первой': 1,
    'второе': 2, 'второй': 2, 'вторую': 2, 'второй': 2,
    'третье': 3, 'третий': 3, 'третью': 3, 'третьей': 3,
    'четвертое': 4, 'четвертый': 4, 'четвертую': 4, 'четвертой': 4,
    'пятое': 5, 'пятый': 5, 'пятую': 5, 'пятой': 5,
    'шестое': 6, 'шестой': 6, 'шестую': 6, 'шестой': 6,
    'седьмое': 7, 'седьмой': 7, 'седьмую': 7, 'седьмой': 7,
    'восьмое': 8, 'восьмой': 8, 'восьмую': 8, 'восьмой': 8,
    'девятое': 9, 'девятый': 9, 'девятую': 9, 'девятой': 9,
    'десятое': 10, 'десятый': 10, 'десятую': 10, 'десятой': 10,
    'одиннадцатое': 11, 'одиннадцатый': 11, 'одиннадцатую': 11, 'одиннадцатой': 11,
    'двенадцатое': 12, 'двенадцатый': 12, 'двенадцатую': 12, 'двенадцатой': 12,
    'тринадцатое': 13, 'тринадцатый': 13, 'тринадцатую': 13, 'тринадцатой': 13,
    'четырнадцатое': 14, 'четырнадцатый': 14, 'четырнадцатую': 14, 'четырнадцатой': 14,
    'пятнадцатое': 15, 'пятнадцатый': 15, 'пятнадцатую': 15, 'пятнадцатой': 15,
    'шестнадцатое': 16, 'шестнадцатый': 16, 'шестнадцатую': 16, 'шестнадцатой': 16,
    'семнадцатое': 17, 'семнадцатый': 17, 'семнадцатую': 17, 'семнадцатой': 17,
    'восемнадцатое': 18, 'восемнадцатый': 18, 'восемнадцатую': 18, 'восемнадцатой': 18,
    'девятнадцатое': 19, 'девятнадцатый': 19, 'девятнадцатую': 19, 'девятнадцатой': 19,
    'двадцатое': 20, 'двадцатый': 20, 'двадцатую': 20, 'двадцатой': 20
}
try:
    import pymorphy3
    MORPH_AVAILABLE = True
except ImportError:
    print("pymorphy3 не установлен. Установите: pip install pymorphy3")
    MORPH_AVAILABLE = False

logging.basicConfig(level=logging.ERROR)

class SmartRecipeBot:
    def __init__(self, recipes_file: str = "recipes.json"):
        self.recipes = self.load_recipes(recipes_file)
        self.last_search_results = []
        self.last_shown_recipe = None
        self.conversation_context = []
        self.session_state = {
            'previous_recipes': [],
            'current_intent': None,
            'search_query': None,
            'waiting_for_selection': False,
            'current_page': 0,
            'all_search_results': []
        }

        # Инициализация pymorphy3
        if MORPH_AVAILABLE:
            self.morph = pymorphy3.MorphAnalyzer()
            print("pymorphy3 загружен для морфологического анализа")
        else:
            self.morph = None
            print("Использую упрощенный анализ без pymorphy3")

        # Словарь синонимов для основных ингредиентов
        self.synonyms = {
            'картофель': ['картошка', 'картошечка', 'картофельный'],
            'картошка': ['картофель', 'картошечка', 'картофельный'],
            'гречка': ['гречневая', 'гречневый', 'гречиха'],
            'гречневая': ['гречка', 'гречневый', 'гречиха'],
            'рыба': ['рыбный', 'рыбка', 'рыбешка'],
            'говядина': ['говяжий', 'говядинка'],
            'свинина': ['свиной', 'свининка'],
            # Убрали проблемные синонимы для риса
            'помидор': ['томат', 'томатный'],
            'огурец': ['огурчик', 'огурцовый'],
            'морковь': ['морковка', 'морковный'],
            'лук': ['луковый', 'луковица'],
            'чеснок': ['чесночный'],
            'перец': ['перцевый'],
            'капуста': ['капустный'],
            'сыр': ['сырный'],
            'яйцо': ['яичный', 'яйца'],
            'молоко': ['молочный'],
            'сметана': ['сметанный'],
            'творог': ['творожный'],
            'мука': ['мучной'],
            'сахар': ['сахарный'],
            'масло': ['масляный'],
            'соль': ['соленый'],
            'шоколад': ['шоколадный'],
            'мед': ['медовый'],
            'орех': ['ореховый'],
            'яблоко': ['яблочный'],
            'груша': ['грушевый'],
            'вишня': ['вишневый'],
            'клубника': ['клубничный'],
            'малина': ['малиновый'],
        }

        # Черный список для проблемных комбинаций
        self.blacklisted_combinations = {
            'рис': ['рисовый', 'рисовая', 'рисовое', 'рисовом']
        }

        print("Инициализирую кулинарного помощника...")
        self.prepare_search_index()
        print("Помощник готов!")

    def load_recipes(self, file_path: str) -> List[Dict[str, Any]]:
        """Загружает рецепты из JSON файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    print(f"Загружено {len(data)} рецептов")
                    return data
                else:
                    return [data]
        except Exception as e:
            print(f"Ошибка загрузки: {e}")
            return []

    def prepare_search_index(self):
        """Подготавливает поисковый индекс с нормализованными словами"""
        print("Анализирую рецепты для поискового индекса...")
        
        # Собираем все уникальные слова из рецептов в нормальной форме
        self.all_recipe_words = set()
        self.recipe_index = {}
        self.normalized_recipe_index = {}
        
        for i, recipe in enumerate(self.recipes):
            title = recipe.get('title', '').lower()
            ingredients = ' '.join([str(ing).lower() for ing in recipe.get('ingredients', [])])
            tags = ' '.join(recipe.get('tags', [])).lower()
            description = recipe.get('description', '').lower()
            
            # Создаем поисковый текст для рецепта
            search_text = f"{title} {ingredients} {tags} {description}"
            self.recipe_index[i] = search_text
            
            # Нормализуем слова для поиска
            normalized_text = self.normalize_text(search_text)
            self.normalized_recipe_index[i] = normalized_text
            
            # Собираем все нормализованные слова из рецептов
            words = re.findall(r'\b\w+\b', normalized_text)
            self.all_recipe_words.update(words)
        
        # Добавляем синонимы в список слов для поиска
        for base_word, synonym_list in self.synonyms.items():
            if base_word in self.all_recipe_words:
                self.all_recipe_words.update(synonym_list)
        
        print(f"Проанализировано {len(self.all_recipe_words)} уникальных нормализованных слов")

    def normalize_text(self, text: str) -> str:
        """Приводит текст к нормальной форме"""
        if not self.morph:
            return text
            
        words = re.findall(r'\b\w+\b', text)
        normalized_words = []
        
        for word in words:
            if len(word) > 2:  # Игнорируем короткие слова
                parsed = self.morph.parse(word)[0]
                normal_form = parsed.normal_form
                normalized_words.append(normal_form)
        
        return ' '.join(normalized_words)

    def normalize_word(self, word: str) -> str:
        """Приводит одно слово к нормальной форме"""
        if not self.morph or len(word) <= 2:
            return word
            
        try:
            parsed = self.morph.parse(word)[0]
            return parsed.normal_form
        except:
            return word

    def expand_with_synonyms(self, word: str) -> List[str]:
        """Расширяет слово синонимами"""
        normalized_word = self.normalize_word(word)
        
        # Для риса возвращаем только само слово, без синонимов
        if normalized_word == 'рис':
            return ['рис']  # Только рис, без рисовый
        
        synonyms = [normalized_word]
        
        # Добавляем синонимы из словаря для других слов
        if normalized_word in self.synonyms:
            synonyms.extend(self.synonyms[normalized_word])
        
        # Также проверяем обратные связи
        for base_word, synonym_list in self.synonyms.items():
            if normalized_word in synonym_list and base_word not in synonyms:
                synonyms.append(base_word)
        
        return list(set(synonyms))
    def extract_search_terms(self, query: str) -> List[str]:
        """Извлекает и нормализует поисковые термины с учетом синонимов"""
        query_lower = query.lower()
        
        # Стоп-слова
        stop_words = {
            'привет', 'пока', 'спасибо', 'пожалуйста', 'давай', 'хочу', 
            'найди', 'покажи', 'рецепт', 'сделать', 'приготовить', 'можно',
            'что', 'как', 'где', 'когда', 'почему', 'это', 'то', 'такой',
            'чтобы', 'ты', 'мне', 'для', 'меня', 'подскажи', 'чтото', 'что-то',
            'нибудь', 'что-нибудь', 'найди', 'найти', 'ищи', 'поиск', 'рецепты',
            'блюда', 'блюдо', 'чего', 'чем', 'чего-нибудь', 'чего-то', 'чтото',
            'что-то', 'то', 'со', 'из', 'для', 'на', 'в', 'с', 'и', 'или', 'у',
            'чего', 'чем', 'какой', 'какая', 'какое', 'какие', 'как', 'такой',
            'грандшеф', 'гранд', 'шеф', 'давай', 'хочу', 'чтото', 'что-то'
        }
        
        # Извлекаем слова из запроса и нормализуем их
        query_words = re.findall(r'\b\w+\b', query_lower)
        
        # Нормализуем слова и фильтруем
        search_terms = []
        for word in query_words:
            if len(word) > 2 and word not in stop_words:
                normalized_word = self.normalize_word(word)
                # Расширяем синонимами
                word_variants = self.expand_with_synonyms(normalized_word)
                
                # Проверяем, есть ли хотя бы один вариант в рецептах
                for variant in word_variants:
                    if variant in self.all_recipe_words:
                        search_terms.append(variant)
                        break
        
        print(f"Нормализованные поисковые термины: {search_terms}")
        return search_terms

    def recipe_matches_search(self, recipe_idx: int, search_terms: List[str]) -> Tuple[bool, int]:
        """Проверяет, соответствует ли рецепт поисковым терминам (по нормализованному индексу)"""
        if not search_terms:
            return False, 0
            
        normalized_recipe_text = self.normalized_recipe_index[recipe_idx]
        recipe_title = self.recipes[recipe_idx].get('title', '').lower()
        normalized_title = self.normalize_text(recipe_title)
        
        # Разбиваем текст рецепта на отдельные слова для точного поиска
        recipe_words = set(re.findall(r'\b\w+\b', normalized_recipe_text))
        title_words = set(re.findall(r'\b\w+\b', normalized_title))
        
        # Уровни совпадения:
        # 3 - все термины в названии
        # 2 - часть терминов в названии + остальные в рецепте
        # 1 - все термины в рецепте (но не в названии)
        # 0 - не совпадает
        
        title_matches = 0
        all_terms_in_recipe = True
        
        for term in search_terms:
            # Для риса используем специальную логику
            if term == 'рис':
                # Для риса ищем только прямое совпадение "рис", игнорируем "рисовый" и т.д.
                term_found_in_title = 'рис' in title_words
                term_found_in_recipe = 'рис' in recipe_words
            else:
                # Для других слов используем обычную логику с синонимами
                term_found_in_title = term in title_words
                term_found_in_recipe = term in recipe_words
                
                if not term_found_in_title:
                    term_variants = self.expand_with_synonyms(term)
                    term_found_in_title = any(variant in title_words for variant in term_variants)
                
                if not term_found_in_recipe:
                    term_variants = self.expand_with_synonyms(term)
                    term_found_in_recipe = any(variant in recipe_words for variant in term_variants)
            
            if term_found_in_title:
                title_matches += 1
            if not term_found_in_recipe:
                all_terms_in_recipe = False
        
        if not all_terms_in_recipe:
            return False, 0
            
        if title_matches == len(search_terms):
            return True, 3  # Все термины в названии
        elif title_matches > 0:
            return True, 2  # Часть терминов в названии
        else:
            return True, 1  # Все термины только в рецепте

    def find_matching_recipes(self, search_terms: List[str]) -> List[Tuple[Dict[str, Any], float]]:
        """Находит рецепты, соответствующие поисковым терминам с правильной сортировкой"""
        results = []
        
        print(f"Ищу рецепты с точными словами: {search_terms}")
        
        for recipe_idx in range(len(self.recipes)):
            recipe = self.recipes[recipe_idx]
            
            # Проверяем соответствие поисковым терминам и получаем уровень совпадения
            matches, match_level = self.recipe_matches_search(recipe_idx, search_terms)
            
            if matches:
                # Базовый score в зависимости от уровня совпадения
                if match_level == 3:
                    score = 1.0  # Максимальный score для совпадения в названии
                elif match_level == 2:
                    score = 0.8  # Высокий score для частичного совпадения в названии
                else:
                    score = 0.6  # Базовый score для совпадения только в рецепте
                
                results.append((recipe, score))
        
        # Сортируем по релевантности (score)
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def smart_search(self, query: str) -> List[Tuple[Dict[str, Any], float]]:
        """Умный поиск рецептов с морфологическим анализом"""
        print(f"Анализирую запрос: '{query}'")

        search_terms = self.extract_search_terms(query)
        print(f"Поисковые термины: {search_terms}")

        self.session_state['search_query'] = query
        self.session_state['waiting_for_selection'] = False

        # Обработка смены темы
        if any(word in query.lower() for word in ['еще', 'дальше', 'следующие', 'покажи еще']):
            if self.session_state['all_search_results']:
                self.session_state['current_page'] += 1
                current_page = self.session_state['current_page']
                all_results = self.session_state['all_search_results']
                
                start_idx = current_page * 5
                end_idx = start_idx + 5
                
                if start_idx < len(all_results):
                    page_results = all_results[start_idx:end_idx]
                    print(f"Показываю страницу {current_page + 1}")
                    return page_results
                else:
                    print("Больше нет результатов")
                    return []
            else:
                return []

        # Новый поиск
        results = self.find_matching_recipes(search_terms)
        
        # Сохраняем все результаты для пагинации
        self.session_state['all_search_results'] = results
        self.session_state['current_page'] = 0

        print(f"Найдено {len(results)} рецептов")
        return results[:5] if results else []

    def generate_response(self, query: str, found_recipes: List[Tuple[Dict[str, Any], float]]) -> str:
        """Генерирует ответ"""
        self.last_search_results = found_recipes

        if not found_recipes:
            search_terms = self.extract_search_terms(query)
            if search_terms:
                return f"Не нашла рецептов, содержащих: {', '.join(search_terms)}"
            else:
                return "Не нашла подходящих рецептов. Попробуйте другие слова."

        # Всегда показываем список, даже если один рецепт
        total_results = len(self.session_state['all_search_results'])
        current_page = self.session_state['current_page']
        shown_count = len(found_recipes)
        
        # ПРАВИЛЬНО вычисляем номера для текущей страницы
        start_number = current_page * 5 + 1
        end_number = start_number + shown_count - 1
        
        return f"Нашла {total_results} рецептов (показано {start_number}-{end_number}):"

    def format_recipe_response(self, recipe: Dict[str, Any]) -> str:
        """Форматирует полный рецепт"""
        response = f"\n\n{recipe.get('title', 'Рецепт')}\n"

        if recipe.get('description'):
            response += f"{recipe['description']}\n\n"

        if recipe.get('temperature'):
            response += f"Температура: {recipe['temperature']}\n"
        if recipe.get('time'):
            response += f"Время: {recipe['time']}\n"

        if recipe.get('ingredients'):
            response += "\nИнгредиенты:\n"
            for ingredient in recipe['ingredients']:
                response += f"  - {ingredient}\n"

        if recipe.get('steps'):
            response += "\nПриготовление:\n"
            for i, step in enumerate(recipe['steps'], 1):
                clean_step = re.sub(r'[▪️️♨️🔥]', '', step).strip()
                if clean_step:
                    response += f"  {i}. {clean_step}\n"

        if recipe.get('tags'):
            response += f"\nКатегории: {', '.join(recipe['tags'])}\n"
        return response

    def format_recipe_list(self, recipes: List[Tuple[Dict[str, Any], float]]) -> str:
        """Форматирует список рецептов"""
        if not recipes:
            return ""

        # Если только один рецепт, все равно показываем список для выбора
        recipes_to_show = recipes
        self.session_state['waiting_for_selection'] = True
        current_page = self.session_state['current_page']
        
        response = []
        for i, (recipe, score) in enumerate(recipes_to_show, 1):
            title = recipe.get('title', 'Рецепт без названия')
            time_info = f" ({recipe['time']})" if recipe.get('time') else ""
            
            # ВАЖНО: Используем глобальный номер, а не локальный для страницы
            global_index = i + 5 * current_page
            response.append(f"{global_index}. {title}{time_info}")

        total_results = len(self.session_state['all_search_results'])
        
        pagination_info = f"\n\nСтраница {current_page + 1} из {((total_results - 1) // 5) + 1}"
        navigation_info = "\nУкажите номер рецепта 1, 2, 3... или название для выбора. Напишите 'другой рецепт' для нового поиска."
        
        return "\n" + "\n".join(response) + pagination_info + navigation_info

    def is_selection_from_list(self, message: str) -> bool:
        """Проверяет, является ли сообщение выбором из списка"""
        if not self.last_search_results or not self.session_state['waiting_for_selection']:
            return False
            
        message_lower = message.lower().strip()
        
        # Игнорируем команды поиска при выборе из списка
        search_commands = ['найди', 'грандшеф найди', 'грандшеф', 'поиск', 'ищи']
        if any(message_lower.startswith(cmd) for cmd in search_commands):
            return False
            
        # Убираем мешающие слова типа "давай", "покажи", "хочу" и т.д.
        filter_words = ['давай', 'покажи', 'хочу', 'выбери', 'можно']
        clean_message = message_lower
        for word in filter_words:
            clean_message = clean_message.replace(word, '').strip()
        
        # Если после очистки сообщение пустое, используем оригинальное
        if not clean_message:
            clean_message = message_lower
            
        # Получаем все результаты для проверки глобальных номеров
        all_results = self.session_state['all_search_results']
        
        # Проверяем номер (цифры) - теперь проверяем глобальные номера
        if clean_message.isdigit():
            number = int(clean_message)
            return 1 <= number <= len(all_results)
        
        # Проверяем словесные обозначения номеров (локальные на странице)
        number_words = NUMBER_WORDS
        
        if clean_message in number_words:
            number = number_words[clean_message]
            return 1 <= number <= len(self.last_search_results)
            
        # Проверяем по названию (среди всех результатов)
        for recipe, score in all_results:
            title = recipe.get('title', '').lower()
            
            # Точное совпадение или частичное
            if clean_message == title or clean_message in title:
                return True
                
        return False

    def select_recipe(self, selection: str) -> Optional[Dict[str, Any]]:
        """Выбирает рецепт по номеру или названию"""
        if not self.last_search_results:
            return None

        selection_lower = selection.lower().strip()

        # Убираем мешающие слова типа "давай", "покажи", "хочу" и т.д.
        filter_words = ['давай', 'покажи', 'хочу', 'выбери', 'можно']
        clean_selection = selection_lower
        for word in filter_words:
            clean_selection = clean_selection.replace(word, '').strip()
        
        # Если после очистки сообщение пустое, используем оригинальное
        if not clean_selection:
            clean_selection = selection_lower

        # Словарь словесных обозначений номеров
        number_words = NUMBER_WORDS

        # Получаем все результаты поиска и текущую страницу
        all_results = self.session_state['all_search_results']
        current_page = self.session_state['current_page']
        
        # Выбор по номеру (цифры) - теперь работаем с глобальными номерами
        if clean_selection.isdigit():
            selected_number = int(clean_selection)
            
            # Проверяем, что номер в пределах общего количества результатов
            if 1 <= selected_number <= len(all_results):
                # Находим рецепт по глобальному номеру
                recipe, score = all_results[selected_number - 1]
                self.session_state['previous_recipes'].append(recipe.get('title'))
                self.session_state['waiting_for_selection'] = False
                return recipe

        # Выбор по словесному номеру - теперь работаем с локальными номерами на странице
        if clean_selection in number_words:
            local_number = number_words[clean_selection]
            # Проверяем, что локальный номер в пределах текущей страницы
            if 1 <= local_number <= len(self.last_search_results):
                recipe, score = self.last_search_results[local_number - 1]
                self.session_state['previous_recipes'].append(recipe.get('title'))
                self.session_state['waiting_for_selection'] = False
                return recipe

        # Выбор по названию (ищем среди всех результатов)
        for recipe, score in all_results:
            title = recipe.get('title', '').lower()
            
            # Точное совпадение или частичное
            if clean_selection == title or clean_selection in title:
                self.session_state['previous_recipes'].append(recipe.get('title'))
                self.session_state['waiting_for_selection'] = False
                return recipe

        return None

    def process_message(self, message: str) -> str:
        """Обрабатывает сообщение пользователя"""
        if not message.strip():
            return "Пожалуйста, опишите, что вы хотите приготовить."

        message_lower = message.lower().strip()

        # Выход из режима выбора по фразе "другой рецепт"
        if self.session_state['waiting_for_selection'] and any(word in message_lower for word in ['другой', 'новый', 'искать', 'поиск', 'найди']):
            self.session_state['waiting_for_selection'] = False
            self.session_state['all_search_results'] = []
            # Если начинается с команды поиска - выполняем поиск
            if any(message_lower.startswith(cmd) for cmd in ['найди', 'грандшеф найди', 'грандшеф', 'поиск', 'ищи']):
                clean_query = message_lower
                for cmd in ['найди', 'грандшеф найди', 'грандшеф', 'поиск', 'ищи']:
                    clean_query = clean_query.replace(cmd, '').strip()
                
                recipes = self.smart_search(clean_query)
                if recipes:
                    main_response = self.generate_response(clean_query, recipes)
                    recipes_formatted = self.format_recipe_list(recipes)
                    return f"{main_response}{recipes_formatted}"
                else:
                    return "Не нашла подходящих рецептов. Попробуйте другие слова."
            else:
                return "Хорошо, давайте поищем другой рецепт. Напишите что вы хотите приготовить."

        # Если в режиме выбора - проверяем выбор
        if self.session_state['waiting_for_selection'] and self.is_selection_from_list(message):
            selected_recipe = self.select_recipe(message)
            if selected_recipe:
                self.last_shown_recipe = selected_recipe.get('title')
                return self.format_recipe_response(selected_recipe)
            else:
                return "Рецепт не найден. Выберите номер или название из списка."

        # Простые команды
        if message_lower in ['привет', 'здравствуйте', 'начать']:
            return "Привет! Я ваш кулинарный помощник. Для поиска рецептов начните сообщение со слов: найди, грандшеф найди, или просто укажите что вы хотите приготовить."
        
        if message_lower in ['пока', 'выход', 'до свидания']:
            return "До свидания! Приятного аппетита!"

        # Проверяем, содержит ли запрос команду для поиска
        search_commands = ['найди', 'грандшеф найди', 'грандшеф', 'поиск', 'ищи']
        has_search_command = any(message_lower.startswith(cmd) for cmd in search_commands)
        
        # Если нет команды поиска и не в режиме выбора - подсказка
        if not has_search_command and not self.session_state['waiting_for_selection']:
            return "Для поиска рецептов начните сообщение со слов: 'найди', 'грандшеф найди' или укажите что вы хотите приготовить."

        # Убираем команды поиска из запроса для чистого анализа
        clean_query = message_lower
        for cmd in search_commands:
            clean_query = clean_query.replace(cmd, '').strip()

        # Поиск рецептов
        recipes = self.smart_search(clean_query)
        if recipes:
            main_response = self.generate_response(clean_query, recipes)
            recipes_formatted = self.format_recipe_list(recipes)
            return f"{main_response}{recipes_formatted}"
        else:
            return "Не нашла подходящих рецептов. Попробуйте другие слова."

    def run_chat(self):
        """Запускает интерактивный чат"""
        print("\n" + "=" * 60)
        print("КУЛИНАРНЫЙ ПОМОЩНИК - УМНЫЙ ПОИСК РЕЦЕПТОВ")
        print("=" * 60)
        print(f"Загружено рецептов: {len(self.recipes)}")
        if MORPH_AVAILABLE:
            print("Использую морфологический анализ для поиска")
            print("Понимает разные формы слов: курицу, курицей, курочка -> курица")
        print("\nИНСТРУКЦИЯ:")
        print("1. Для поиска начните сообщение с: 'найди', 'грандшеф найди'")
        print("2. Примеры: 'найди курицу с картошкой', 'грандшеф найди шоколадный торт'")
        print("3. При выборе из списка можно:")
        print("   - Указать номер рецепта (1, 2, 3...)")
        print("   - Написать название рецепта (без 'найди')")
        print("   - Написать 'другой рецепт' или 'найди ...' для нового поиска")
        print("4. Для продолжения поиска: 'покажи еще'")
        print("=" * 60)
        print("Начните с команды 'найди' и укажите что хотите приготовить...")

        while True:
            try:
                user_input = input("\nВы: ").strip()

                if user_input.lower() in ['пока', 'выход', 'до свидания', 'закончить']:
                    print(f"\nБот: До свидания! Приятного аппетита!")
                    break

                response = self.process_message(user_input)
                print(f"\nБот: {response}")

            except KeyboardInterrupt:
                print(f"\nБот: До свидания! Приятного аппетита!")
                break
            except Exception as e:
                print(f"\nБот: Извините, произошла ошибка. Попробуйте еще раз.")
                logging.error(f"Error: {e}")

if __name__ == "__main__":
    bot = SmartRecipeBot("recipes.json")
    bot.run_chat()