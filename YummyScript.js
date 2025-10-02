// ==UserScript==
// @name         ЯммиАвтоСвапАкк
// @namespace    http://tampermonkey.net/
// @version      2.9.7
// @description  Смотри Акки на Ямитрекер а потом их автосвапает (требуются доп файлы)
// @author       You
// @match        https://yummytrackstat.com/your-bizzare-adventure
// @icon         https://www.google.com/s2/favicons?sz=64&domain=yummytrackstat.com
// @grant        GM_xmlhttpRequest
// @connect      your_lan_api
// @connect      *
// ==/UserScript==

(function() {
    'use strict';

    // --- Configuration ---
    const SOURCE_RAM_SETTINGS = {
        host: "your_lan_api",
        port: 7963,
        password: "your_pass"
    };

    const TARGET_SERVER_SETTINGS = {
        host: "your_lan_api",
        port: 8081  // Порт для отправки кук
    };

    const CONTROL_SERVER_SETTINGS = {
        host: "your_lan_api",
        port: 8080  // Порт для /exit и /launch
    };

    const TRIGGER_SERVER_SETTINGS = {
        host: "your_lan_api",
        port: 5000  // Порт для /trigger
    };

    const CHECK_INTERVAL_MINUTES = 5;
    const MONEY_THRESHOLD = 1000000; // 1M
    const BATCH_TRIGGER_COUNT = 10; // Количество "полных" аккаунтов для срабатывания отправки

    const DEBUG_MODE = false; //если хотите чтобы все действия комментировались в консоль браузре (f12)
    // --- Конец настроек ---


    // --- Глобальные переменные ---
    let fullAccounts = new Set(); // Аккаунты, которые уже достигли порога и помечены как "FULL"
    let isChecking = false;
    let lastCheckTime = 0;
    const CHECK_COOLDOWN_MS = 30000; // 30 секунд
    let checkIntervalId = null;

    // --- Функции отладки ---
    function debugLog(message, data = null) {
        if (DEBUG_MODE) {
            const timestamp = new Date().toISOString();
            console.log(`[DEBUG ${timestamp}] ${message}`, data || '');
        }
    }

    function logMoneyFound(username, moneyStr, parsedMoney) {
        debugLog(`💰 Найдены деньги для ${username}: "${moneyStr}" -> ${parsedMoney}`);
    }

    function logAccountProcessing(account) {
        debugLog(`📋 Обработка аккаунта: ${account.username}, Деньги: ${account.money}`);
    }

    function logThresholdCheck(account) {
        const status = account.money >= MONEY_THRESHOLD ? '✅ ДОСТИГНУТ' : '❌ НЕ ДОСТИГНУТ';
        debugLog(`📊 Проверка порога для ${account.username}: ${account.money} >= ${MONEY_THRESHOLD} ${status}`);
    }

    // --- Функции ---

    function parseMoneyString(moneyStr) {
        if (!moneyStr) return 0;
        debugLog(`🔄 Парсинг строки денег: "${moneyStr}"`);
        const cleanStr = moneyStr.replace(/[^\d.,KMBkmb]/g, '').trim().toUpperCase();
        if (!cleanStr) return 0;
        let numberPart = cleanStr;
        let multiplier = 1;
        debugLog(`🧹 Очищенная строка: "${cleanStr}"`);

        if (cleanStr.endsWith('K')) {
            numberPart = cleanStr.slice(0, -1);
            multiplier = 1000;
            debugLog(`📈 Найден суффикс K, множитель: ${multiplier}`);
        } else if (cleanStr.endsWith('M')) {
            numberPart = cleanStr.slice(0, -1);
            multiplier = 1000000;
            debugLog(`📈 Найден суффикс M, множитель: ${multiplier}`);
        } else if (cleanStr.endsWith('B')) {
            numberPart = cleanStr.slice(0, -1);
            multiplier = 1000000000;
            debugLog(`📈 Найден суффикс B, множитель: ${multiplier}`);
        }

        let normalizedNumberStr = numberPart.replace(/,/g, '');
        debugLog(`🔢 Нормализованная строка числа: "${normalizedNumberStr}"`);

        const numberValue = parseFloat(normalizedNumberStr);
        if (isNaN(numberValue)) {
            console.warn(`[PARSE MONEY] Could not parse: '${moneyStr}' -> '${cleanStr}' -> '${normalizedNumberStr}'`);
            return 0;
        }

        const result = numberValue * multiplier;
        debugLog(`🔢 Результат парсинга: ${numberValue} * ${multiplier} = ${result}`);
        return result;
    }

    function ensureOnlineTabActive() {
        return new Promise((resolve) => {
            debugLog("🔍 Поиск кнопки вкладки Online");
            const allRadioButtons = document.querySelectorAll('button[role="radio"]');
            debugLog(`📊 Найдено radio кнопок: ${allRadioButtons.length}`);

            allRadioButtons.forEach((btn, index) => {
                const text = btn.textContent.trim();
                const value = btn.getAttribute('value');
                const isChecked = btn.getAttribute('aria-checked');
                debugLog(`🔘 Radio кнопка ${index}: текст="${text}", значение="${value}", активна=${isChecked}`);
            });

            let onlineTabButton = Array.from(document.querySelectorAll('button[role="radio"]'))
                .find(btn => btn.getAttribute('value') === 'online');

            if (!onlineTabButton) {
                debugLog("🔄 Пробуем альтернативные селекторы");
                onlineTabButton = Array.from(document.querySelectorAll('button[role="radio"]'))
                    .find(btn => btn.textContent.trim().toLowerCase() === 'online');

                if (!onlineTabButton) {
                    onlineTabButton = Array.from(document.querySelectorAll('button[role="radio"]'))
                        .find(btn => btn.getAttribute('value')?.toLowerCase().includes('online'));
                }
            }

            if (!onlineTabButton) {
                console.warn("[TAB] Online tab button not found.");
                resolve(false);
                return;
            }

            const isAlreadyActive = onlineTabButton.getAttribute('aria-checked') === 'true';
            debugLog(`🔘 Статус вкладки Online: ${isAlreadyActive ? 'Активна' : 'Не активна'}`);

            if (isAlreadyActive) {
                debugLog("✅ Вкладка Online уже активна");
                resolve(true);
                return;
            }

            debugLog("👆 Кликаем для активации вкладки Online");
            debugLog("📍 Элемент вкладки:", onlineTabButton);
            onlineTabButton.click();

            setTimeout(() => {
                const isActiveNow = onlineTabButton.getAttribute('aria-checked') === 'true';
                debugLog(`🔄 Статус вкладки после клика: ${isActiveNow ? 'Активна' : 'Не активна'}`);
                resolve(isActiveNow);
            }, 1000);
        });
    }

    async function extractAccountData() {
        const accounts = [];
        debugLog("🚀 Начало извлечения данных аккаунтов");

        try {
            const isTabActive = await ensureOnlineTabActive();
            if (!isTabActive) {
                console.error("[EXTRACT] Could not activate Online tab. Aborting extraction.");
                return accounts;
            }

            debugLog("⏳ Ожидание обновления содержимого страницы");
            await new Promise(resolve => setTimeout(resolve, 1500));

            debugLog("🔍 Поиск таблицы");
            let table = document.querySelector('table.w-full.caption-bottom');

            if (!table) {
                debugLog("⚠️ Основная таблица не найдена, пробуем альтернативные селекторы");
                const tableSelectors = [
                    'table.w-full',
                    '.rounded-md.border table',
                    'table[data-testid*="table"]',
                    'table[role="table"]',
                    '[class*="table"]'
                ];

                for (const selector of tableSelectors) {
                    table = document.querySelector(selector);
                    if (table) {
                        debugLog(`✅ Найдена таблица селектором: ${selector}`);
                        break;
                    }
                }
            }

            if (!table) {
                debugLog("⚠️ Таблица не найдена, пробуем найти по содержимому");
                const allTables = document.querySelectorAll('table');
                for (const t of allTables) {
                    const headers = t.querySelectorAll('th');
                    const headerTexts = Array.from(headers).map(h => h.textContent.toLowerCase());
                    if (headerTexts.some(text => text.includes('account') || text.includes('money'))) {
                        table = t;
                        debugLog("✅ Найдена таблица по содержимому заголовков");
                        break;
                    }
                }
            }

            if (!table) {
                console.warn("[EXTRACT] Main table element not found.");
                return accounts;
            }

            debugLog("🔍 Поиск заголовков таблицы");
            const headerRow = table.querySelector('thead tr') || table.querySelector('tr');
            if (!headerRow) {
                console.warn("[EXTRACT] Header row not found in table.");
                return accounts;
            }

            const headers = headerRow.querySelectorAll('th');
            debugLog(`📊 Найдено заголовков: ${headers.length}`);

            headers.forEach((header, index) => {
                const headerText = header.textContent.trim().toLowerCase();
                const imgSrc = header.querySelector('img')?.src || '';
                debugLog(`📋 Заголовок ${index}: текст="${headerText}", img="${imgSrc.substring(0, 50)}"`);
            });

            let accountIndex = -1;
            let moneyIndex = -1;

            headers.forEach((header, index) => {
                const headerText = header.textContent.trim().toLowerCase();
                debugLog(`📋 Заголовок ${index}: '${headerText}'`);
                if (headerText.includes('account') || headerText.includes('аккаунт')) {
                    accountIndex = index;
                    debugLog(`🏷️ Найдена колонка Account: индекс ${index}`);
                }
                const moneyImg = header.querySelector('img[src*="money"], img[src*="coin"], img[src*="gold"]');
                if (moneyImg || headerText.includes('money') || headerText.includes('coin') || headerText.includes('gold')) {
                    moneyIndex = index;
                    debugLog(`💰 Найдена колонка Money: индекс ${index} (текст: "${headerText}")`);
                }
            });

            if (accountIndex === -1 || moneyIndex === -1) {
                console.error(`[EXTRACT] Could not find required columns. Account: ${accountIndex}, Money: ${moneyIndex}`);
                headers.forEach((h, i) => debugLog(`[DEBUG] Header ${i}: '${h.textContent.trim()}'`));
                return accounts;
            }

            debugLog(`✅ Найдены колонки - Account: ${accountIndex}, Money: ${moneyIndex}`);

            let bodyRows = table.querySelectorAll('tbody tr');
            if (bodyRows.length === 0) {
                debugLog("⚠️ tbody не найден, пробуем найти строки напрямую");
                bodyRows = table.querySelectorAll('tr');
                bodyRows = Array.from(bodyRows).slice(1);
            }

            debugLog(`📊 Найдено строк данных: ${bodyRows.length}`);

            if (bodyRows.length === 0) {
                debugLog("⚠️ Таблица пуста");
                return accounts;
            }

            bodyRows.forEach((row, rowIndex) => {
                debugLog(`📝 Обработка строки ${rowIndex + 1}`);
                const cells = row.querySelectorAll('td');
                debugLog(`📊 Ячеек в строке ${rowIndex + 1}: ${cells.length}`);

                if (cells.length <= Math.max(accountIndex, moneyIndex)) {
                    debugLog(`⚠️ Строка ${rowIndex + 1} пропущена: недостаточно ячеек (${cells.length})`);
                    return;
                }

                const accountCell = cells[accountIndex];
                let username = '';
                debugLog(`👤 Ячейка Account (${rowIndex + 1}):`, accountCell?.outerHTML?.substring(0, 200));

                const usernameSpan = accountCell?.querySelector('span.text-sm.font-medium');
                if (usernameSpan) {
                    username = usernameSpan.textContent.trim();
                    debugLog(`👤 Найден username (span): "${username}"`);
                } else {
                    username = accountCell?.textContent?.trim()?.split('\n')[0]?.trim() || '';
                    debugLog(`👤 Найден username (альтернативно): "${username}"`);
                }

                if (!username) {
                    debugLog(`⚠️ Не удалось извлечь username из строки ${rowIndex + 1}`);
                    return;
                }

                const moneyCell = cells[moneyIndex];
                let money = 0;
                let moneyText = '';

                debugLog(`💵 Ячейка Money (${rowIndex + 1}):`, moneyCell?.outerHTML?.substring(0, 200));

                const moneySpan = moneyCell?.querySelector('span.border.text-sm');
                if (moneySpan) {
                    moneyText = moneySpan.textContent.trim();
                    debugLog(`💵 Найден текст денег (span): "${moneyText}"`);
                    money = parseMoneyString(moneyText);
                    logMoneyFound(username, moneyText, money);
                } else {
                    debugLog(`⚠️ Не найден span денег в строке ${rowIndex + 1}`);
                    moneyText = moneyCell?.textContent?.trim() || '';
                    debugLog(`💵 Найден текст денег (ячейка): "${moneyText}"`);
                    money = parseMoneyString(moneyText);
                    logMoneyFound(username, moneyText, money);
                }

                accounts.push({ username, money });
                debugLog(`✅ Добавлен аккаунт: ${username} = ${money}`);
            });

        } catch (error) {
            console.error("[EXTRACT] An error occurred during data extraction:", error);
            debugLog(`❌ Ошибка извлечения данных: ${error.message}`, error.stack);
        }

        debugLog(`🏁 Итоговый список аккаунтов (${accounts.length} шт.):`, accounts);
        return accounts;
    }

    function callRAMApi(endpoint, params = {}) {
        const urlParams = new URLSearchParams(params);
        if (SOURCE_RAM_SETTINGS.password) {
            urlParams.set('Password', SOURCE_RAM_SETTINGS.password);
        }
        const url = `http://${SOURCE_RAM_SETTINGS.host}:${SOURCE_RAM_SETTINGS.port}${endpoint}?${urlParams}`;

        debugLog(`📡 Вызов RAM API: ${url}`);

        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: "GET",
                url: url,
                onload: function(response) {
                    debugLog(`📥 Ответ от RAM API (${response.status}):`, response.responseText);
                    if (response.status === 200) {
                        try {
                            const data = JSON.parse(response.responseText);
                            resolve(data);
                        } catch (e) {
                            if (endpoint === "/GetCookie" || endpoint === "/GetDescription") {
                                resolve(response.responseText);
                            } else {
                                reject(new Error(`Failed to parse JSON response: ${e.message}`));
                            }
                        }
                    } else {
                        reject(new Error(`RAM API error (${response.status}): ${response.statusText}`));
                    }
                },
                onerror: function(error) {
                    debugLog(`❌ Ошибка сети при вызове RAM API:`, error);
                    reject(new Error(`Network error calling RAM API: ${error}`));
                }
            });
        });
    }

    async function isAccountInRAM(username) {
        try {
            debugLog(`🔍 Проверка наличия аккаунта в RAM: ${username}`);
            const accountListResponse = await callRAMApi("/GetAccounts");
            const accountsInRAM = accountListResponse.split(',').map(name => name.trim()).filter(name => name);
            const exists = accountsInRAM.includes(username);
            debugLog(`📊 Аккаунт ${username} ${exists ? 'найден' : 'НЕ найден'} в RAM`);
            return exists;
        } catch (error) {
            console.error(`[RAM CHECK] Error for '${username}':`, error);
            return true; // Предполагаем, что есть, если ошибка
        }
    }

    async function setDescriptionInRAM(username, description) {
        try {
            debugLog(`📝 Установка описания для аккаунта ${username}: ${description}`);

            const urlParams = new URLSearchParams();
            if (SOURCE_RAM_SETTINGS.password) {
                urlParams.set('Password', SOURCE_RAM_SETTINGS.password);
            }
            urlParams.set('Account', username);
            const url = `http://${SOURCE_RAM_SETTINGS.host}:${SOURCE_RAM_SETTINGS.port}/SetDescription?${urlParams.toString()}`;

            const requestBody = JSON.stringify({ Description: description });

            debugLog(`📡 Вызов RAM API: POST ${url}`, `Body: ${requestBody}`);

            return new Promise((resolve, reject) => {
                GM_xmlhttpRequest({
                    method: "POST",
                    url: url,
                    data: requestBody,
                    headers: {
                        "Content-Type": "application/json"
                    },
                    onload: function(response) {
                        debugLog(`📥 Ответ от RAM API (${response.status}):`, response.responseText.substring(0, 200));
                        if (response.status === 200) {
                            debugLog(`✅ Описание для ${username} успешно установлено: ${description}`);
                            resolve(true);
                        } else {
                            console.error(`[SET DESCRIPTION ERROR] Failed for ${username}. Status: ${response.status}`, response.responseText);
                            reject(new Error(`Failed to set description: ${response.status}`));
                        }
                    },
                    onerror: function(error) {
                        debugLog(`❌ Ошибка сети при установке описания для ${username}:`, error);
                        reject(new Error(`Network error setting description: ${error}`));
                    }
                });
            });
        } catch (error) {
            console.error(`[SET DESCRIPTION] Exception for '${username}':`, error);
            return false;
        }
    }

    async function getCookieFromRAM(username) {
        try {
            debugLog(`🍪 Получение куки для аккаунта: ${username}`);
            const cookieResponse = await callRAMApi("/GetCookie", { Account: username });
            // Проверяем, не является ли ответ пустым или ошибкой
            if (cookieResponse && typeof cookieResponse === 'string' && cookieResponse.trim() !== '') {
                 debugLog(`🔑 Куки для ${username}: ${cookieResponse.substring(0, 50)}...`);
                 return cookieResponse;
            } else {
                debugLog(`⚠️ Куки для ${username} пустые или не получены.`);
                return null;
            }
        } catch (error) {
            console.error(`[GET COOKIE] Error for '${username}':`, error);
            return null;
        }
    }

    /**
     * Отправляет куки на сервер другого ПК.
     * Отправляет только куки, без дополнительных данных.
     */
    function sendCookieToTargetPC(username, cookie) {
        // Отправляем только куки как текст в теле запроса
        debugLog(`📤 Отправка куки на другой ПК (только куки): ${username}`, cookie ? `${cookie.substring(0, 50)}...` : 'COOKIE IS NULL');

        const url = `http://${TARGET_SERVER_SETTINGS.host}:${TARGET_SERVER_SETTINGS.port}/receive_cookie`;

        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: "POST",
                url: url,
                data: cookie, // <-- ИСПРАВЛЕНО: используем 'data' вместо 'cookie'
                headers: {
                    "Content-Type": "text/plain" // Меняем тип контента
                },
                onload: function(response) {
                    if (response.status === 200) {
                        debugLog(`✅ Куки успешно отправлены на другой ПК: ${username}`);
                        resolve(response);
                    } else {
                        console.error(`[SEND COOKIE ERROR] Failed for ${username}. Status: ${response.status}`, response.responseText);
                        reject(new Error(`Failed to send cookie: ${response.status}`));
                    }
                },
                onerror: function(error) {
                    debugLog(`❌ Ошибка сети при отправке куки на другой ПК ${username}:`, error);
                    reject(new Error(`Network error sending cookie: ${error}`));
                }
            });
        });
    }

    async function getAccountsWithDescriptions() {
        try {
            debugLog("📋 Получение списка аккаунтов с описаниями из RAM");
            const accountsResponse = await callRAMApi("/GetAccountsJson");
            debugLog(`📊 Получено ${accountsResponse.length} аккаунтов из RAM`);
            return accountsResponse;
        } catch (error) {
            console.error("[GET ACCOUNTS WITH DESCRIPTIONS] Error:", error);
            return [];
        }
    }

    /**
     * Получает список аккаунтов из RAM, у которых нет описания.
     * Эти аккаунты готовы к отправке.
     */
    async function getAccountsWithoutDescription(limit = BATCH_TRIGGER_COUNT) {
        try {
            debugLog(`📋 Получение списка аккаунтов без описания из RAM (лимит: ${limit})`);
            const ramAccounts = await getAccountsWithDescriptions();
            const availableAccounts = [];

            for (const ramAccount of ramAccounts) {
                const username = ramAccount.Username;
                const description = ramAccount.Description || "";

                if (!description || description.trim() === "") {
                    availableAccounts.push(username);
                    debugLog(`➕ Добавлен аккаунт ${username} в список доступных для отправки`);
                }

                if (availableAccounts.length >= limit) {
                    break;
                }
            }

            debugLog(`✅ Найдено ${availableAccounts.length} аккаунтов без описания для отправки:`, availableAccounts);
            return availableAccounts;
        } catch (error) {
            console.error("[GET ACCOUNTS WITHOUT DESCRIPTION] Error:", error);
            return [];
        }
    }

    /**
     * Отправляет куки для указанного списка аккаунтов.
     * Возвращает Promise, разрешающийся количеством успешно отправленных кук.
     */
    async function sendCookiesForAccounts(accountList) {
        debugLog(`📤 Начало отправки куки для ${accountList.length} аккаунтов:`, accountList);

        let successCount = 0;
        // Обрабатываем аккаунты последовательно, чтобы избежать перегрузки
        for (const username of accountList) {
            debugLog(`📤 Обработка аккаунта для отправки: ${username}`);
            try {
                const cookie = await getCookieFromRAM(username);
                if (cookie) {
                    debugLog(`✅ Куки успешно получены для ${username}`);
                    // Отправляем куки
                    await sendCookieToTargetPC(username, cookie);
                    debugLog(`✅ Куки для ${username} успешно отправлены на сервер.`);
                    successCount++;
                } else {
                    const errorMsg = `⚠️ Не удалось получить куки для ${username} или куки пустые.`;
                    debugLog(errorMsg);
                    // Не увеличиваем successCount
                }
            } catch (error) {
                const errorMsg = `⚠️ Ошибка при обработке аккаунта ${username}: ${error.message}`;
                debugLog(errorMsg);
                // Не увеличиваем successCount
                // Продолжаем обработку следующих аккаунтов
            }
        }

        debugLog(`🏁 Отправка куки для партии завершена. Успешно отправлено: ${successCount}/${accountList.length}.`);
        // Возвращаем количество успешно отправленных кук
        return successCount;
    }


    // --- НОВЫЕ ФУНКЦИИ ДЛЯ ДОПОЛНИТЕЛЬНЫХ ДЕЙСТВИЙ ---

    /**
     * Отправляет GET-запрос на указанный URL.
     * @param {string} url - URL для отправки запроса.
     * @returns {Promise} - Promise, который разрешается при успешном ответе.
     */
    function sendGetRequest(url) {
        return new Promise((resolve, reject) => {
            debugLog(`📡 Отправка GET-запроса: ${url}`);
            GM_xmlhttpRequest({
                method: "GET",
                url: url,
                onload: function(response) {
                    debugLog(`📥 Ответ от ${url} (${response.status}):`, response.responseText);
                    if (response.status >= 200 && response.status < 300) {
                        resolve(response);
                    } else {
                        reject(new Error(`HTTP error ${response.status}: ${response.statusText}`));
                    }
                },
                onerror: function(error) {
                    debugLog(`❌ Ошибка сети при отправке запроса ${url}:`, error);
                    reject(new Error(`Network error calling ${url}: ${error}`));
                }
            });
        });
    }

    /**
     * Выполняет последовательность действий после отправки куки:
     * 1. Отправляет /exit на порт 8080
     * 2. Ждет 10 секунд
     * 3. Отправляет /launch на порт 8080
     * 4. Отправляет /trigger на порт 5000
     */
    async function performPostBatchActions() {
        debugLog("🚀 Начало выполнения действий после отправки куки");
        try {
            // 1. Отправить /exit на порт 8080
            const exitUrl = `http://${CONTROL_SERVER_SETTINGS.host}:${CONTROL_SERVER_SETTINGS.port}/exit`;
            await sendGetRequest(exitUrl);
            debugLog("✅ Команда /exit отправлена успешно");

            // 2. Подождать 10 секунд
            debugLog("⏳ Ожидание 10 секунд...");
            await new Promise(resolve => setTimeout(resolve, 10000));

            // 3. Отправить /launch на порт 8080
            const launchUrl = `http://${CONTROL_SERVER_SETTINGS.host}:${CONTROL_SERVER_SETTINGS.port}/launch`;
            await sendGetRequest(launchUrl);
            debugLog("✅ Команда /launch отправлена успешно");

            // 4. Отправить /trigger на порт 5000
            const triggerUrl = `http://${TRIGGER_SERVER_SETTINGS.host}:${TRIGGER_SERVER_SETTINGS.port}/trigger`;
            await sendGetRequest(triggerUrl);
            debugLog("✅ Команда /trigger отправлена успешно");

            debugLog("🏁 Все действия после отправки куки выполнены успешно");
        } catch (error) {
            console.error("[POST BATCH ACTIONS] Ошибка при выполнении действий:", error);
            debugLog(`❌ Ошибка в performPostBatchActions: ${error.message}`);
            // Не останавливаем основной поток, продолжаем проверки
        }
    }

    /**
     * Основная функция проверки аккаунтов.
     */
    async function checkAccounts() {
        const now = Date.now();
        if (isChecking) {
            debugLog("⏭️ Проверка уже выполняется, пропускаем");
            return;
        }

        if ((now - lastCheckTime) < CHECK_COOLDOWN_MS) {
             debugLog(`⏱️ Кулдаун активен. Последняя проверка: ${((now - lastCheckTime) / 1000).toFixed(1)}с назад`);
             return;
        }

        isChecking = true;
        lastCheckTime = now;
        debugLog("🚀 Запуск цикла проверки аккаунтов");

        try {
            // 1. Получаем данные с сайта
            const accountsOnPage = await extractAccountData();

            // 2. Проверяем, достигли ли аккаунты порога
            let newFullAccountsCount = 0;
            for (const account of accountsOnPage) {
                logAccountProcessing(account);

                if (isNaN(account.money)) {
                    debugLog(`⚠️ Значение денег для ${account.username} является NaN. Пропускаем.`);
                    continue;
                }

                logThresholdCheck(account);

                // Проверяем, не был ли аккаунт уже помечен как "FULL"
                if (fullAccounts.has(account.username)) {
                    debugLog(`⏭️ Аккаунт ${account.username} уже в списке "полных". Пропускаем.`);
                    continue;
                }

                if (account.money >= MONEY_THRESHOLD) {
                    debugLog(`🎉 Порог достигнут для ${account.username}: ${account.money} >= ${MONEY_THRESHOLD}`);
                    const existsInRAM = await isAccountInRAM(account.username);
                    if (existsInRAM) {
                        debugLog(`✅ Аккаунт ${account.username} подтвержден в RAM.`);

                        // Установить описание "FULL"
                        try {
                            await setDescriptionInRAM(account.username, "FULL");
                            debugLog(`✅ Описание установлено для ${account.username}`);

                            // Добавляем аккаунт в список "полных"
                            fullAccounts.add(account.username);
                            newFullAccountsCount++;
                            debugLog(`💾 Аккаунт ${account.username} добавлен в список "полных"`);
                        } catch (error) {
                            debugLog(`⚠️ Не удалось установить описание для ${account.username}:`, error.message);
                        }
                    } else {
                        debugLog(`⚠️ Аккаунт ${account.username} достиг порога, но НЕ найден в RAM. Пропускаем.`);
                    }
                } else {
                    debugLog(`📉 ${account.username}: ${account.money} < ${MONEY_THRESHOLD} - ниже порога`);
                }
            }

            debugLog(`📊 Новых "полных" аккаунтов за этот цикл: ${newFullAccountsCount}`);
            debugLog(`📊 Общее количество "полных" аккаунтов: ${fullAccounts.size}`);

            // 3. Проверяем, нужно ли отправлять куки
            if (fullAccounts.size >= BATCH_TRIGGER_COUNT) {
                debugLog(`🎉 Достигнуто пороговое количество "полных" аккаунтов (${fullAccounts.size} >= ${BATCH_TRIGGER_COUNT}). Инициируем отправку куки.`);

                // Получаем список аккаунтов без описания для отправки
                const accountsToSend = await getAccountsWithoutDescription(BATCH_TRIGGER_COUNT);
                if (accountsToSend.length >= BATCH_TRIGGER_COUNT) {
                    // Отправляем куки и ждем результата
                    const sentCount = await sendCookiesForAccounts(accountsToSend);
                    debugLog(`✅ Обработано аккаунтов: ${sentCount}.`);

                    // --- ИЗМЕНЕНА ЛОГИКА ---
                    // Выполняем дополнительные действия после отправки куки
                    // только если все 8 кук были успешно отправлены.
                    if (sentCount === BATCH_TRIGGER_COUNT) {
                        await performPostBatchActions();
                        debugLog("✅ Выполнены действия после отправки куки.");
                    } else {
                        debugLog(`⚠️ Не все куки были отправлены успешно (${sentCount}/${BATCH_TRIGGER_COUNT}), пропускаем performPostBatchActions.`);
                    }
                    // --- КОНЕЦ ИЗМЕНЕНИЙ ---

                } else {
                    debugLog(`⚠️ Недостаточно аккаунтов без описания для отправки (${accountsToSend.length} < ${BATCH_TRIGGER_COUNT}). Отправка отменена.`);
                }

                // Очищаем список "полных" аккаунтов после отправки
                // Аккаунты без описания будут обработаны внешним сервером
                fullAccounts.clear();
                debugLog(`🗑️ Список "полных" аккаунтов очищен.`);
            } else {
                 debugLog(`⏳ Количество "полных" аккаунтов (${fullAccounts.size}) меньше порога (${BATCH_TRIGGER_COUNT}). Ожидаем следующего цикла.`);
            }

        } catch (error) {
            console.error("[ERROR] During check cycle:", error);
        } finally {
            isChecking = false;
            debugLog("🏁 Цикл проверки аккаунтов завершен");
        }
    }

    function stopPeriodicChecks() {
        if (checkIntervalId) {
            clearInterval(checkIntervalId);
            checkIntervalId = null;
            debugLog("⏹️ Периодические проверки остановлены");
        }
    }

    function startPeriodicChecks() {
        if (checkIntervalId) {
            debugLog("▶️ Проверки уже запущены");
            return;
        }
        const intervalMs = CHECK_INTERVAL_MINUTES * 60 * 1000;
        debugLog(`▶️ Планирование периодических проверок каждые ${CHECK_INTERVAL_MINUTES} минут (${intervalMs} мс)`);
        checkIntervalId = setInterval(checkAccounts, intervalMs);
        setTimeout(checkAccounts, 2000); // Первая проверка через 2 секунды
    }

    function init() {
        console.log("[INIT] YummyAuto Money Tracker & Account Switch Notifier v2.9.7 (Batch Send & Post Actions)");
        debugLog("🔧 Инициализация скрипта");
        debugLog("⚙️ Конфигурация:", {
            SOURCE_RAM_SETTINGS,
            TARGET_SERVER_SETTINGS,   // Порт 8081 для кук
            CONTROL_SERVER_SETTINGS,  // Порт 8080 для /exit и /launch
            TRIGGER_SERVER_SETTINGS,  // Порт 5000 для /trigger
            CHECK_INTERVAL_MINUTES,
            MONEY_THRESHOLD,
            BATCH_TRIGGER_COUNT,
            DEBUG_MODE
        });

        const waitForContent = setInterval(() => {
            const tableContainer = document.querySelector('div.rounded-md.border') ||
                                  document.querySelector('table.w-full.caption-bottom') ||
                                  document.querySelector('table');
            if (tableContainer) {
                clearInterval(waitForContent);
                debugLog("✅ Контент страницы загружен. Запуск проверок.");
                startPeriodicChecks();
            } else {
                debugLog("⏳ Ожидание загрузки контента страницы...");
            }
        }, 1000);

        setTimeout(() => {
            if (!checkIntervalId) {
                clearInterval(waitForContent);
                console.error("[INIT] Page content did not load within 30 seconds. Script may not work correctly.");
                debugLog("⚠️ Контент не загрузился за 30 секунд, но пробуем запустить проверки");
                startPeriodicChecks();
            }
        }, 30000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    window.addEventListener('beforeunload', () => {
        stopPeriodicChecks();
    });

})();
