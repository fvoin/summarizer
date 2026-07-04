"""Lightweight i18n module for macOS Summarizer.

Detects the macOS system language and provides a simple ``t(key)`` lookup.
"""

import subprocess
from functools import lru_cache
from typing import Dict

_STRINGS: Dict[str, Dict[str, str]] = {
    # ── App titles & window names ────────────────────────────────────────
    "app_title":                {"en": "Summarizer",                          "ru": "Summarizer"},
    "settings_title":           {"en": "Settings",                            "ru": "Settings"},

    # ── Main window labels ───────────────────────────────────────────────
    "context_label":            {"en": "Meeting series:",                     "ru": "Серия встреч:"},
    "context_none":             {"en": "(none)",                              "ru": "(нет)"},
    "context_add_tooltip":      {"en": "Create new named context",            "ru": "Создать новый контекст"},
    "context_edit_tooltip":     {"en": "Edit context file in default editor", "ru": "Открыть файл контекста в редакторе"},
    "context_delete_tooltip":   {"en": "Delete selected context",             "ru": "Удалить выбранный контекст"},
    "general_context_label":    {"en": "Persistent context",                  "ru": "Постоянный контекст"},
    "general_context_placeholder": {
        "en": "Key info: meeting type, goals, usual participants, key terms…",
        "ru": "Ключевая информация: тип встреч, цели, обычные участники, ключевые термины…",
    },
    "meeting_context_label":    {"en": "This meeting context",                "ru": "Контекст этой встречи"},
    "meeting_context_placeholder": {
        "en": "Agenda, attendees, specific details for this meeting…",
        "ru": "Повестка, участники, детали для этой встречи…",
    },
    "instructions_label":       {"en": "Instructions:",                       "ru": "Инструкции:"},
    "start_recording":          {"en": "  Start Recording",                   "ru": "  Начать запись"},
    "stop_recording":           {"en": "  Stop  {time}",                      "ru": "  Стоп  {time}"},
    "summarize_audio":          {"en": "Summarize Audio File",                "ru": "Суммировать аудио"},
    "summarize_transcript":     {"en": "Summarize Transcript",                "ru": "Суммировать текст"},
    "drop_hint":                {"en": "drag & drop or click to open audio / text files",
                                 "ru": "перетащите или нажмите для открытия аудио / текстовых файлов"},
    "copy_summary":             {"en": "  Copy Summary",                      "ru": "  Копировать итог"},
    "copy_transcript":          {"en": "  Copy Transcript",                   "ru": "  Копировать транскрипт"},
    "open_transcript":          {"en": "  Open Transcript",                   "ru": "  Открыть транскрипт"},
    "update_context":           {"en": "Update Context",                      "ru": "Обновить контекст"},
    "summary_placeholder":      {"en": "Summary will appear here…",           "ru": "Итог появится здесь…"},
    "transcript_placeholder":   {"en": "Transcript will appear here…",        "ru": "Транскрипт появится здесь…"},
    "live_transcript_placeholder": {
        "en": "Live transcript will appear here while recording…",
        "ru": "Транскрипт в реальном времени появится здесь во время записи…",
    },
    "settings_tooltip":         {"en": "Settings",                            "ru": "Настройки"},

    # ── Status messages ──────────────────────────────────────────────────
    "status_recording":         {"en": "Recording…",                          "ru": "Запись…"},
    "status_recording_agent":   {"en": "Recording (web): {title}",            "ru": "Запись (веб): {title}"},
    "status_transcribing":      {"en": "Transcribing…",                       "ru": "Транскрибирование…"},
    "status_summarizing":       {"en": "Summarizing…",                        "ru": "Суммирование…"},
    "status_done":              {"en": "Done",                                "ru": "Готово"},
    "status_copied":            {"en": "Copied to clipboard",                 "ru": "Скопировано в буфер обмена"},
    "status_context_updated":   {"en": "Context updated",                     "ru": "Контекст обновлён"},
    "status_no_transcript":     {"en": "No transcript file available",        "ru": "Файл транскрипта недоступен"},
    "status_unsupported_file":  {"en": "Unsupported file type",               "ru": "Неподдерживаемый тип файла"},
    "status_recording_failed":  {"en": "Recording failed — no audio captured",
                                 "ru": "Ошибка записи — звук не захвачен"},
    "status_finishing":         {"en": "Finishing last few seconds…",          "ru": "Обработка последних секунд…"},
    "status_processing":        {"en": "Processing recording…",               "ru": "Обработка записи…"},
    "status_silence":           {"en": "Silence detected — ",                 "ru": "Обнаружена тишина — "},

    # ── Error messages ───────────────────────────────────────────────────
    "error_title":              {"en": "Error",                               "ru": "Ошибка"},
    "error_no_speech": {
        "en": (
            "No speech detected in the recording.\n\n"
            "Possible reasons:\n"
            "- The recording was too short\n"
            "- Microphone didn't capture audio (check Input Device in Settings)\n"
            "- Audio was too quiet"
        ),
        "ru": (
            "Речь в записи не обнаружена.\n\n"
            "Возможные причины:\n"
            "- Запись была слишком короткой\n"
            "- Микрофон не захватил звук (проверьте устройство ввода в Настройках)\n"
            "- Звук был слишком тихий"
        ),
    },
    "error_read_file":          {"en": "Failed to read file: {error}",        "ru": "Не удалось прочитать файл: {error}"},
    "error_file_empty":         {"en": "File is empty",                       "ru": "Файл пуст"},

    # ── Dialogs ──────────────────────────────────────────────────────────
    "new_context_title":        {"en": "New Meeting Series",                  "ru": "Новая серия встреч"},
    "new_context_prompt":       {"en": "Meeting series name:",                "ru": "Название серии встреч:"},
    "delete_context_title":     {"en": "Delete Meeting Series",               "ru": "Удалить серию встреч"},
    "delete_context_confirm":   {"en": "Delete meeting series '{name}'?",     "ru": "Удалить серию встреч «{name}»?"},

    # ── Settings dialog ──────────────────────────────────────────────────
    "tab_models":               {"en": "Models",                              "ru": "Модели"},
    "tab_instructions":         {"en": "Instructions",                        "ru": "Инструкции"},
    "tab_general":              {"en": "General",                             "ru": "Общие"},
    "tab_advanced":             {"en": "Advanced",                            "ru": "Расширенные"},
    "ai_model_group":           {"en": "AI Model",                            "ru": "Модель ИИ"},
    "cloud_label":              {"en": "☁  Cloud",                            "ru": "☁  Облачные"},
    "custom_label":             {"en": "Custom:",                             "ru": "Другая:"},
    "api_key_label":            {"en": "API Key:",                            "ru": "API-ключ:"},
    "api_key_placeholder":      {"en": "your API key",                        "ru": "ваш API-ключ"},
    "base_url_label":           {"en": "Base URL:",                           "ru": "Адрес API:"},
    "base_url_placeholder":     {"en": "(optional)",                          "ru": "(необязательно)"},
    "local_label":              {"en": "⚡  Local (Ollama)",                   "ru": "⚡  Локальные (Ollama)"},
    "ollama_not_found": {
        "en": "Ollama not found — click Download to auto-install, or visit <a href='https://ollama.com'>ollama.com</a>",
        "ru": "Ollama не найден — нажмите Скачать для установки или посетите <a href='https://ollama.com'>ollama.com</a>",
    },
    "model_placeholder":        {"en": "model name…",                         "ru": "название модели…"},
    "whisper_group":            {"en": "Whisper Model (speech recognition)",   "ru": "Модель Whisper (распознавание речи)"},
    "context_limit_label":      {"en": "Context Limit:",                      "ru": "Лимит контекста:"},
    "silence_timeout_label":    {"en": "Silence Timeout:",                    "ru": "Таймаут тишины:"},
    "input_device_label":       {"en": "Input Device:",                       "ru": "Устройство ввода:"},
    "input_device_default":     {"en": "System default",                      "ru": "Системный по умолчанию"},
    "device_default":           {"en": "Default",                             "ru": "По умолчанию"},
    "save_audio_label":         {"en": "Save Audio:",                         "ru": "Сохранять аудио:"},
    "save_audio_check":         {"en": "Save recorded audio files to recordings dir",
                                 "ru": "Сохранять аудиофайлы в папку записей"},
    "mode_label":               {"en": "Mode:",                               "ru": "Режим:"},
    "transcribe_only_check":    {"en": "Transcribe only (no summarization)",  "ru": "Только транскрипция (без суммирования)"},
    "sound_label":              {"en": "Sound:",                              "ru": "Звук:"},
    "sound_check":              {"en": "Play sound when done",                "ru": "Воспроизводить звук по завершении"},
    "recordings_dir_label":     {"en": "Recordings Dir:",                     "ru": "Папка записей:"},
    "recordings_dir_placeholder": {
        "en": "(default: ~/.summarizer/recordings)",
        "ru": "(по умолчанию: ~/.summarizer/recordings)",
    },
    "diagnostics_label":        {"en": "Diagnostics:",                        "ru": "Диагностика:"},
    "open_log":                 {"en": "Open Log File",                       "ru": "Открыть лог"},
    "theme_label":              {"en": "Theme:",                              "ru": "Тема:"},
    "theme_light":              {"en": "Light",                               "ru": "Светлая"},
    "theme_dark":               {"en": "Dark",                                "ru": "Тёмная"},
    "theme_nord":               {"en": "Nord",                                "ru": "Nord"},
    "theme_restart_hint":       {"en": "Restart the app to apply the theme.", "ru": "Перезапустите приложение для применения темы."},
    "version_label":            {"en": "Version:",                            "ru": "Версия:"},
    "check_updates":            {"en": "Check for Updates",                   "ru": "Проверить обновления"},
    "checking_updates":         {"en": "Checking…",                           "ru": "Проверка…"},
    "downloading_update":       {"en": "Downloading…",                        "ru": "Загрузка…"},
    "save_btn":                 {"en": "Save",                                "ru": "Сохранить"},
    "cancel_btn":               {"en": "Cancel",                              "ru": "Отмена"},
    "new_btn":                  {"en": "New",                                 "ru": "Новый"},
    "delete_btn":               {"en": "Delete",                              "ru": "Удалить"},
    "instructions_placeholder": {"en": "System instructions for the LLM agent…",
                                 "ru": "Системные инструкции для ИИ-агента…"},

    # ── Settings dialogs & messages ──────────────────────────────────────
    "logs_title":               {"en": "Logs",                                "ru": "Логи"},
    "logs_no_file":             {"en": "No log file yet — run the app first.",
                                 "ru": "Лог-файла ещё нет — сначала запустите приложение."},
    "update_available_title":   {"en": "Update Available",                    "ru": "Доступно обновление"},
    "update_available_msg": {
        "en": "A new version {tag} is available.\n\n{notes}\n\nDownload now?",
        "ru": "Доступна новая версия {tag}.\n\n{notes}\n\nСкачать сейчас?",
    },
    "up_to_date_title":         {"en": "Up to Date",                          "ru": "Обновлений нет"},
    "up_to_date_msg": {
        "en": "You are running the latest version (v{version}).",
        "ru": "У вас установлена последняя версия (v{version}).",
    },
    "update_check_failed":      {"en": "Update Check Failed",                 "ru": "Ошибка проверки обновлений"},
    "update_ready_title":       {"en": "Update Ready",                        "ru": "Обновление готово"},
    "update_ready_msg":         {"en": "New version downloaded!",             "ru": "Новая версия загружена!"},
    "update_install_instructions": {
        "en": (
            "To install:\n"
            "1. Click \"Quit & Open DMG\" below\n"
            "2. Drag Summarizer to Applications\n"
            "3. Launch Summarizer from Applications"
        ),
        "ru": (
            "Для установки:\n"
            "1. Нажмите «Выйти и открыть DMG» ниже\n"
            "2. Перетащите Summarizer в Программы\n"
            "3. Запустите Summarizer из Программ"
        ),
    },
    "quit_open_dmg":            {"en": "Quit & Open DMG",                     "ru": "Выйти и открыть DMG"},
    "later_btn":                {"en": "Later",                               "ru": "Позже"},
    "download_failed":          {"en": "Download Failed",                     "ru": "Ошибка загрузки"},
    "new_profile_title":        {"en": "New Profile",                         "ru": "Новый профиль"},
    "new_profile_prompt":       {"en": "Profile name:",                       "ru": "Название профиля:"},
    "delete_profile_title":     {"en": "Delete Profile",                      "ru": "Удалить профиль"},
    "delete_profile_confirm":   {"en": "Delete profile «{name}»?",           "ru": "Удалить профиль «{name}»?"},
    "bundled_model_title":      {"en": "Bundled Model",                       "ru": "Встроенная модель"},
    "bundled_model_msg": {
        "en": "'{name}' is bundled with the app and cannot be deleted.",
        "ru": "«{name}» встроена в приложение и не может быть удалена.",
    },
    "delete_whisper_title":     {"en": "Delete Whisper Model",                "ru": "Удалить модель Whisper"},
    "delete_whisper_confirm":   {"en": "Delete '{name}' model files from disk?",
                                 "ru": "Удалить файлы модели «{name}» с диска?"},
    "ollama_required_title":    {"en": "Ollama Required",                     "ru": "Требуется Ollama"},
    "ollama_required_msg": {
        "en": (
            "Ollama is required for local models.\n\n"
            "Auto-install (will install Homebrew too if needed)\n"
            "or download manually from ollama.com."
        ),
        "ru": (
            "Для локальных моделей необходим Ollama.\n\n"
            "Автоустановка (при необходимости установит Homebrew)\n"
            "или скачайте вручную с ollama.com."
        ),
    },
    "auto_install_btn":         {"en": "Auto Install",                        "ru": "Установить автоматически"},
    "open_download_page":       {"en": "Open Download Page",                  "ru": "Открыть страницу загрузки"},
    "installing_ollama":        {"en": "Installing Ollama…",                  "ru": "Установка Ollama…"},
    "ollama_ready":             {"en": "Ollama ready",                        "ru": "Ollama готов"},
    "not_downloaded":           {"en": "Not downloaded",                      "ru": "Не загружено"},
    "ollama_install_failed":    {"en": "Ollama Install Failed",               "ru": "Ошибка установки Ollama"},
    "local_model_error":        {"en": "Local Model Error",                   "ru": "Ошибка локальной модели"},
    "delete_local_title":       {"en": "Delete Local Model",                  "ru": "Удалить локальную модель"},
    "delete_local_confirm":     {"en": "Delete '{name}' from Ollama?",        "ru": "Удалить «{name}» из Ollama?"},
    "model_not_downloaded_title": {"en": "Model Not Downloaded",              "ru": "Модель не загружена"},
    "model_not_downloaded_msg": {
        "en": (
            "'{name}' is not downloaded yet.\n"
            "It will be downloaded automatically on first transcription.\n\n"
            "Save anyway?"
        ),
        "ru": (
            "Модель «{name}» ещё не загружена.\n"
            "Она будет загружена автоматически при первой транскрипции.\n\n"
            "Всё равно сохранить?"
        ),
    },

    # ── Model row strings ────────────────────────────────────────────────
    "model_download":           {"en": "Download",                            "ru": "Скачать"},
    "model_downloading":        {"en": "Downloading…",                        "ru": "Загрузка…"},
    "model_ready":              {"en": "Ready",                               "ru": "Готово"},
    "model_delete":             {"en": "Delete",                              "ru": "Удалить"},
    "model_test":               {"en": "Test",                                "ru": "Тест"},
    "model_pulling":            {"en": "Downloading…",                        "ru": "Загрузка…"},
    "model_error":              {"en": "Error",                               "ru": "Ошибка"},

    # ── Setup wizard ─────────────────────────────────────────────────────
    "wizard_title":             {"en": "Welcome to Summarizer",               "ru": "Добро пожаловать в Summarizer"},
    "wizard_subtitle": {
        "en": "Let's set up your AI model to get started.",
        "ru": "Давайте настроим модель ИИ для начала работы.",
    },
    "wizard_cloud_title":       {"en": "Cloud LLM — Gemini, GPT, Claude via API",
                                 "ru": "Облачная модель — Gemini, GPT, Claude через API"},
    "wizard_cloud_desc":        {"en": "Fast, high quality. Requires an API key (Gemini is free).",
                                 "ru": "Быстро и качественно. Нужен API-ключ (Gemini бесплатно)."},
    "wizard_local_title":       {"en": "Local LLM — runs on your Mac, fully offline",
                                 "ru": "Локальная модель — работает на вашем Mac, полностью оффлайн"},
    "wizard_local_desc":        {"en": "No API key needed. Requires 8+ GB RAM.",
                                 "ru": "Без API-ключа. Нужно 8+ ГБ RAM."},
    "wizard_cloud_step_title":  {"en": "Cloud API Setup",                     "ru": "Настройка облачного API"},
    "wizard_gemini_label": {
        "en": "Gemini API Key  <span style='color:#6e6e73; font-weight:400;'>(recommended — free)</span>",
        "ru": "Gemini API-ключ  <span style='color:#6e6e73; font-weight:400;'>(рекомендуется — бесплатно)</span>",
    },
    "wizard_key_placeholder":   {"en": "Paste your Gemini API key here…",     "ru": "Вставьте ваш Gemini API-ключ сюда…"},
    "wizard_key_hint": {
        "en": "Get a free key at <a href=\"https://aistudio.google.com/apikey\" style=\"color:{color};\">aistudio.google.com/apikey</a>",
        "ru": "Получите бесплатный ключ на <a href=\"https://aistudio.google.com/apikey\" style=\"color:{color};\">aistudio.google.com/apikey</a>",
    },
    "wizard_local_step_title":  {"en": "Choose a Local Model",               "ru": "Выберите локальную модель"},
    "wizard_local_step_desc": {
        "en": "Select a model to download. It will run entirely on your Mac.",
        "ru": "Выберите модель для загрузки. Она будет работать полностью на вашем Mac.",
    },
    "wizard_recommended":       {"en": "Recommended",                         "ru": "Рекомендуется"},
    "wizard_use_step_title": {
        "en": "What will you use Summarizer for?",
        "ru": "Для чего вы будете использовать Summarizer?",
    },
    "wizard_work_title":        {"en": "Work Meetings",                       "ru": "Рабочие встречи"},
    "wizard_work_desc": {
        "en": "Structured summaries with action items,\ndecisions, risks, and cost estimates.",
        "ru": "Структурированные итоги с задачами,\nрешениями, рисками и оценкой стоимости.",
    },
    "wizard_general_title":     {"en": "General Meetings",                    "ru": "Общие встречи"},
    "wizard_general_desc": {
        "en": "Concise summaries focused on key points\nand takeaways. Less formal.",
        "ru": "Краткие итоги с фокусом на ключевые моменты\nи выводы. Менее формально.",
    },
    "wizard_skip":              {"en": "Skip for now",                        "ru": "Пропустить"},
    "wizard_back":              {"en": "Back",                                "ru": "Назад"},
    "wizard_next":              {"en": "Next",                                "ru": "Далее"},
    "wizard_finish":            {"en": "Finish",                              "ru": "Завершить"},

    # ── Instruction profile names ────────────────────────────────────────
    "profile_work":             {"en": "Work Meetings",                       "ru": "Рабочие встречи"},
    "profile_general":          {"en": "General Meetings",                    "ru": "Общие встречи"},

    # ── File dialog titles ───────────────────────────────────────────────
    "open_audio_title":         {"en": "Open Audio File",                     "ru": "Открыть аудиофайл"},
    "open_transcript_title":    {"en": "Open Transcript",                     "ru": "Открыть транскрипт"},

    "wizard_whisper_title":     {"en": "Choose a Whisper Model",               "ru": "Выберите модель Whisper"},
    "wizard_whisper_desc":      {"en": "Whisper converts speech to text locally. Larger models are more accurate but slower.",
                                 "ru": "Whisper распознаёт речь локально. Большие модели точнее, но медленнее."},
    "wizard_bundled":           {"en": "bundled",                              "ru": "в комплекте"},
    "wizard_download_title":    {"en": "Download Models",                      "ru": "Загрузка моделей"},
    "wizard_download_desc":     {"en": "The following models need to be downloaded:",
                                 "ru": "Необходимо загрузить следующие модели:"},
    "wizard_download_now":      {"en": "Download Now",                         "ru": "Скачать сейчас"},
    "wizard_downloading_models": {"en": "Downloading…",                        "ru": "Загрузка…"},
    "wizard_download_complete": {"en": "All downloads complete!",              "ru": "Все загрузки завершены!"},
    "wizard_download_error":    {"en": "Download error: {error}",              "ru": "Ошибка загрузки: {error}"},
    "wizard_llm_type_title":    {"en": "Choose AI Model Type",                 "ru": "Выберите тип модели ИИ"},

    # ── OllamaChatDialog ─────────────────────────────────────────────────
    "chat_title":               {"en": "Chat with {name}",                    "ru": "Чат с {name}"},
    "chat_placeholder":         {"en": "Type a message…",                     "ru": "Введите сообщение…"},
    "chat_send":                {"en": "Send",                                "ru": "Отправить"},
    "context_chat_title":       {"en": "Chat about meeting series",            "ru": "Чат о серии встреч"},
    "context_chat_tooltip":     {"en": "Chat about this context",             "ru": "Чат об этом контексте"},
    "context_chat_system":      {
        "en": "You are a helpful assistant. Answer questions about this meeting series based on the context below.\n\n{context}",
        "ru": "Ты — полезный ассистент. Отвечай на вопросы о серии встреч на основе контекста ниже.\n\n{context}",
    },
    "btn_yes":                  {"en": "Yes",                                 "ru": "Да"},
    "btn_no":                   {"en": "No",                                  "ru": "Нет"},

    # ── History dialog ───────────────────────────────────────────────────
    "history_title":            {"en": "Meeting History",                     "ru": "История встреч"},
    "history_tooltip":          {"en": "Meeting history",                     "ru": "История встреч"},
    "history_col_context":      {"en": "Meeting series",                     "ru": "Серия встреч"},
    "history_col_date":         {"en": "Date",                               "ru": "Дата"},
    "history_col_duration":     {"en": "Duration",                           "ru": "Длительность"},
    "history_col_actions":      {"en": "Actions",                            "ru": "Действия"},
    "history_context":          {"en": "Context",                             "ru": "Контекст"},
    "history_transcript":       {"en": "Transcript",                         "ru": "Транскрипт"},
    "history_summary":          {"en": "Summary",                            "ru": "Саммари"},
    "history_empty":            {"en": "No meetings recorded yet.",          "ru": "Пока нет записанных встреч."},
    "history_view_title":       {"en": "{type} — {title}",                   "ru": "{type} — {title}"},
    "history_change_series_tt": {"en": "Click to change meeting series",     "ru": "Нажмите, чтобы изменить серию"},
    "history_change_series":    {"en": "Move meeting to series",             "ru": "Переместить встречу в серию"},
    "history_no_series":        {"en": "— No series —",                      "ru": "— Без серии —"},
    "history_new_series":       {"en": "+ New series…",                      "ru": "+ Новая серия…"},
    "history_no_series_short":  {"en": "—",                                  "ru": "—"},

    # ── Context editor dialog ────────────────────────────────────────────
    "ctx_editor_title":         {"en": "Edit meeting series — {name}",       "ru": "Редактировать серию встреч — {name}"},
    "ctx_editor_persistent":    {"en": "Persistent context",                 "ru": "Постоянный контекст"},
    "ctx_editor_meetings":      {"en": "Meetings",                           "ru": "Встречи"},
    "ctx_editor_edit":          {"en": "Edit",                               "ru": "Редактировать"},
    "ctx_editor_save":          {"en": "Save",                               "ru": "Сохранить"},
    "ctx_editor_no_meetings":   {"en": "No meetings for this context yet.",  "ru": "Пока нет встреч для этого контекста."},

    # ── Menu bar / Tray ─────────────────────────────────────────────────
    "tray_show":                {"en": "Show {name}",                         "ru": "Показать {name}"},
    "tray_start_rec":           {"en": "Start Recording",                     "ru": "Начать запись"},
    "tray_stop_rec":            {"en": "Stop Recording",                      "ru": "Остановить запись"},
    "tray_settings":            {"en": "Settings…",                           "ru": "Настройки…"},
    "tray_quit":                {"en": "Quit",                                "ru": "Выход"},
    "tray_recording":           {"en": "Recording…",                          "ru": "Запись…"},
    "tray_processing":          {"en": "Processing…",                         "ru": "Обработка…"},

    # ── Menu bar settings ───────────────────────────────────────────────
    "menubar_label":            {"en": "Menu bar:",                           "ru": "Строка меню:"},
    "menubar_check":            {"en": "Enable menu bar icon",                "ru": "Показывать в строке меню"},

    # ── Agent settings ──────────────────────────────────────────────────
    "agent_group":              {"en": "Recording Agent",                     "ru": "Агент записи"},
    "agent_url_label":          {"en": "Backend URL:",                        "ru": "URL бэкенда:"},
    "agent_url_placeholder":    {"en": "https://app.example.com",             "ru": "https://app.example.com"},
    "agent_token_label":        {"en": "Token:",                              "ru": "Токен:"},
    "agent_token_placeholder":  {"en": "Paste token from web app settings",   "ru": "Вставьте токен из настроек веб-приложения"},
    "agent_enabled_check":      {"en": "Auto-record upcoming meetings",       "ru": "Автозапись предстоящих встреч"},
    "agent_test_btn":           {"en": "Test Connection",                     "ru": "Проверить соединение"},
    "agent_test_ok":            {"en": "Connected! {count} upcoming meeting(s).", "ru": "Подключено! Встреч в ближайшее время: {count}."},
    "agent_test_fail":          {"en": "Connection failed: {error}",          "ru": "Ошибка соединения: {error}"},
    "agent_notify_armed":       {"en": "Will record: {title}",               "ru": "Будет записано: {title}"},
    "agent_notify_recording":   {"en": "Recording: {title}",                 "ru": "Запись: {title}"},
    "agent_notify_uploaded":    {"en": "Uploaded: {title}",                   "ru": "Загружено: {title}"},
    "agent_notify_noshow":      {"en": "No voice detected, skipped: {title}", "ru": "Голос не обнаружен, пропущено: {title}"},
    "agent_notify_error":       {"en": "Agent error: {error}",               "ru": "Ошибка агента: {error}"},

    # ── Lite window ──────────────────────────────────────────────────────
    "lite_title": {"en": "Transcriber", "ru": "Transcriber"},
    "lite_ready": {"en": "Ready", "ru": "Готово"},
    "lite_placeholder": {"en": "Transcript will appear here.",
                          "ru": "Транскрипт появится здесь."},
    "lite_copy": {"en": "Copy transcript", "ru": "Копировать транскрипт"},
    "lite_copied": {"en": "Copied to clipboard", "ru": "Скопировано в буфер обмена"},
    "lite_done": {"en": "Transcript ready", "ru": "Транскрипт готов"},
    "lite_error": {"en": "Transcription failed: {err}", "ru": "Ошибка транскрипции: {err}"},
    "lite_update_btn": {"en": "Update", "ru": "Обновить"},
    "lite_update_avail": {"en": "Update available: {ver}", "ru": "Доступно обновление: {ver}"},
    "lite_updating": {"en": "Downloading update…", "ru": "Загрузка обновления…"},
    "lite_update_done": {"en": "Opening installer…", "ru": "Открываю установщик…"},
    "lite_agent_waiting": {"en": "Waiting for scheduled meetings…",
                            "ru": "Ожидание запланированных встреч…"},
    "lite_agent_countdown": {"en": "Auto-record «{title}» in {mins} min",
                              "ru": "Автозапись «{title}» через {mins} мин"},
    "lite_agent_recording": {"en": "Auto-recording: {title}",
                              "ru": "Автозапись: {title}"},
    "lite_uploaded": {"en": "Transcript uploaded", "ru": "Транскрипт загружен"},
    "lite_upload_failed": {"en": "Upload failed: {err}", "ru": "Ошибка загрузки: {err}"},

    # ── Lite setup wizard ────────────────────────────────────────────────
    "lite_setup_title": {"en": "Set up Transcriber", "ru": "Настройка Transcriber"},
    "lite_setup_mic": {"en": "Choose your microphone. Grant mic access if prompted.",
                        "ru": "Выберите микрофон. Разрешите доступ к микрофону при запросе."},
    "lite_setup_url": {"en": "Backend URL", "ru": "URL бэкенда"},
    "lite_setup_token": {"en": "Access token", "ru": "Токен доступа"},
    "lite_setup_download": {"en": "Downloading the transcription model…",
                             "ru": "Загрузка модели транскрипции…"},
}


@lru_cache(maxsize=1)
def locale() -> str:
    """Return ``'ru'`` if the macOS primary language is Russian, otherwise ``'en'``."""
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleLanguages"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            # The first non-paren line that looks like a language code is the primary one
            for line in lines:
                lang = line.strip().strip('(",)')
                if lang:
                    if lang.startswith("ru"):
                        return "ru"
                    break
    except Exception:
        pass
    return "en"


def t(key: str, **kwargs: object) -> str:
    """Return the translated string for *key*, formatted with *kwargs*."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(locale(), entry.get("en", key))
    if kwargs:
        text = text.format(**kwargs)
    return text
