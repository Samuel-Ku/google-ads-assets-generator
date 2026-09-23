# Runbook розгортання Google Ads Assets Studio

Цей документ описує, де працює сервіс, як випустити нову версію та як повернутися до попередньої. Він призначений для майбутнього обслуговування. Дані кампаній і секрети не зберігаються в репозиторії або в архіві релізу.

## Де працює сервіс

Сервіс розміщений на внутрішній Ubuntu VM:

- SSH: ubuntu@192.168.15.42
- URL для офісної мережі або корпоративного VPN: http://192.168.15.42:8765/
- systemd unit: google-ads-assets.service
- процес: один Waitress-процес, Python із VM virtualenv
- обробка зображень: CPU; платні AI API не використовуються
- доступ: тільки приватна LAN/VPN-адреса; публічний port-forward і пряме відкриття в інтернет не налаштовані

Станом на 22 вересня 2026 року активний реліз:

    /home/ubuntu/google-ads-assets/releases/20260921-150038

Перевірка стану:

    ssh -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu@192.168.15.42 \
      'systemctl is-active google-ads-assets.service && readlink /home/ubuntu/google-ads-assets/current && df -h /'

Очікуваний стан сервісу — active. Перед новим релізом потрібен запас вільного місця щонайменше 1 GiB для системи; поточна VM має обмежений диск, тому не накопичуйте старі архіви або копії медіа.

## Структура VM

    /home/ubuntu/google-ads-assets/
    ├── current -> releases/<release>       # активний реліз
    ├── next                                  # тимчасове посилання під час перемикання
    ├── previous-release                     # ім'я попереднього релізу
    ├── releases/<YYYYMMDD-HHMMSS>/         # незмінні файли кожного релізу
    ├── venv/                               # ізольоване Python-середовище
    ├── data/                               # SQLite, сесійний секрет, медіа, ZIP
    ├── service.env                         # приватна конфігурація, mode 600
    └── pre-template-library-*.sqlite3     # контрольні копії бази, якщо створені перед міграцією

Робочий каталог systemd — current. Запис дозволений лише в data/; unit додатково використовує ProtectSystem=strict, PrivateTmp, NoNewPrivileges, ліміт пам'яті 1500 MiB і 64 задачі.

У service.env зберігаються runtime-налаштування:

    ADS_DATA_DIR=/home/ubuntu/google-ads-assets/data
    ADS_QUOTA_BYTES=1073741824
    ADS_RESERVE_BYTES=1073741824
    ADS_COOKIE_SECURE=0
    ADS_TRUSTED_HOSTS=192.168.15.42,127.0.0.1,localhost
    STUDIO_BIND=192.168.15.42
    STUDIO_PORT=8765
    PYTHONDONTWRITEBYTECODE=1

Сесійний секрет і пароль адміністратора не потрібно переносити в реліз. Не виводьте їх у термінал, логи, issue або чат.

## Що потрапляє в реліз

scripts/deploy.py створює allowlist-архів із застосунку, шаблонів, статичних файлів, моделі U²-NetP, storage.py, template_library.py, unit-файлу та основної документації. Локальні дані, SQLite, ACCESS-PRIVATE.txt, virtualenv, тести й тимчасові файли в реліз не копіюються.

Скрипт перед перемиканням перевіряє:

1. наявність VM virtualenv і понад 1.8 GB вільного місця;
2. доступність defusedxml і tinycss2;
3. компіляцію Python-модулів;
4. SHA-256 моделі models/u2netp.onnx;
5. перемикання симлінка та перезапуск лише google-ads-assets.service.

## Плановий deploy

Виконуйте команди з кореня проєкту на робочій машині.

### 1. Перевірити локальний стан

    .venv/bin/python -m pytest -q
    /Users/MARKETING1/.nvm/versions/node/v22.22.0/bin/node --check static/app.js
    /Users/MARKETING1/.nvm/versions/node/v22.22.0/bin/node --check static/canvas.js
    /Users/MARKETING1/.nvm/versions/node/v22.22.0/bin/node tests/format-sync.cjs
    /Users/MARKETING1/.nvm/versions/node/v22.22.0/bin/node tests/frontend-materials.cjs
    /Users/MARKETING1/.nvm/versions/node/v22.22.0/bin/node tests/template-recipes.cjs

Перед релізом також потрібен браузерний smoke test: логін, відкриття тестової/існуючої кампанії, перегляд матеріалу, композиція, preview і пробний ZIP. Не змінюйте реальні кампанії під час тесту — використовуйте ізольовані fixtures.

### 2. Перевірити VM і створити backup перед міграцією

    ssh -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu@192.168.15.42 \
      'systemctl is-active google-ads-assets.service; readlink /home/ubuntu/google-ads-assets/current; df -h /'

Перед зміною схеми SQLite створіть узгоджену копію з коротким описом релізу. Backup зберігайте в data/ лише тимчасово, із правами 600, і не копіюйте його в архів релізу. Не видаляйте єдину копію бази, поки новий реліз не пройшов перевірку.

### 3. Dry run

    .venv/bin/python scripts/deploy.py

Dry run лише показує ціль, кількість allowlisted entries і правила. Він не змінює VM.

### 4. Застосувати реліз

    .venv/bin/python scripts/deploy.py --apply

Скрипт створює новий каталог releases/<UTC timestamp>, копіює allowlist, перевіряє модулі й модель, записує previous-release, атомарно перемикає current, виконує systemctl daemon-reload і перезапускає сервіс. Інші systemd units, nginx, DNS і firewall не змінюються.

### 5. Перевірити після deploy

    ssh -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu@192.168.15.42 \
      'systemctl is-active google-ads-assets.service; readlink /home/ubuntu/google-ads-assets/current; journalctl -u google-ads-assets.service -n 60 --no-pager'

Після цього відкрийте http://192.168.15.42:8765/ через офіс або VPN і перевірте: логін, список кампаній, Brand Kit, захищене завантаження матеріалу, композицію, збереження версії, preview та ZIP. Переконайтеся, що data/ зберігся і старі кампанії не зникли.

## Rollback

Rollback потрібен, якщо сервіс не запускається або smoke test виявив регресію.

    ssh -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu@192.168.15.42
    cd /home/ubuntu/google-ads-assets
    readlink current
    cat previous-release
    sudo -n systemctl stop google-ads-assets.service
    ln -sfn "$(cat previous-release)" next
    mv -Tf next current
    sudo -n systemctl start google-ads-assets.service
    sudo -n systemctl is-active google-ads-assets.service

Безпечніший варіант — вказати повний відомий шлях попереднього релізу замість значення з файлу, якщо previous-release неочікуваний. Після rollback перевірте логи та UI. Не видаляйте data/, не робіть git reset --hard на VM і не видаляйте production campaign media для виправлення помилки коду.

Rollback коду не є rollback даних. Якщо реліз уже виконав міграцію, відновлюйте SQLite лише за окремою процедурою з узгодженою backup-копією; спершу зупиніть сервіс і переконайтеся, що копія відповідає потрібному моменту.

## Дані, retention і місце

- Media кампаній і ZIP автоматично видаляються через 7 днів.
- Brand Kit, текстова історія та записи кампаній залишаються довше й займають місце.
- Квота застосунку — 1 GiB; резерв вільного диска — 1 GiB.
- Cleanup торкається лише каталогів і записів цього сервісу.
- Не зберігайте постійні backup-архіви на цій VM; переносьте їх у погоджене окреме сховище.
- Після великих тестів перевіряйте df -h / і /api/storage через авторизований UI/API.

## Діагностика

    sudo -n systemctl status google-ads-assets.service --no-pager
    sudo -n journalctl -u google-ads-assets.service -n 120 --no-pager
    df -h /
    ss -ltn

Типові причини проблем:

- current вказує не на новий реліз — перевірте атомарне перемикання і previous-release;
- сервіс не стартує — перевірте py_compile, virtualenv, unit і логи;
- deploy зупинився на preflight — спочатку звільніть місце, не зменшуйте reserve;
- UI не відкривається — перевірте, що клієнт у LAN/VPN і порт 8765 не зайнятий іншим процесом;
- помилка фонового видалення — перевірте CPU/пам'ять і чергу job, не запускайте другий процес застосунку.

## Відповідальність і правила

Deploy робить лише уповноважений оператор із доступом до VM. Не публікуйте URL назовні, не передавайте SSH-ключі або пароль адміністратора, не перезапускайте інші сервіси і не редагуйте production SQLite вручну без backup та окремого плану відновлення.

Пов'язана технічна процедура в репозиторії: scripts/deploy.py. Цей runbook є операційною інструкцією; якщо він розходиться з кодом deploy-скрипта, спочатку перевірте скрипт і зафіксуйте зміну в документації.
