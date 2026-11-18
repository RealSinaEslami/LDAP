# HTG LDAP API

## اجرا

اطلاعات اتصال ارائه‌شده در فایل `.env` تنظیم شده است؛ در صورت تغییر رمز، آن را در همین فایل به‌روزرسانی کنید.
کلید تصادفی `API_KEY` در همین فایل تولید شده است؛ مقدارش را برای Swagger نگه دارید.
فایل `.env` در Git نادیده گرفته می‌شود و رمز داخل کد قرار ندارد.

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
```

صفحهٔ http://127.0.0.1:8000/docs را باز کنید. در Authorize مقدار API_KEY را وارد کنید.

- `POST /data/sync`: خواندن تمام کاربران محدودهٔ LDAP و ثبت یا به‌روزرسانی در SQLite.
- `GET /data/users`: نمایش کاربران با offset، limit و q برای جست‌وجوی نام کاربری.
- `GET /data/users/{uid}`: دریافت کاربر با objectGUID.
- `GET /health`: سلامت برنامه؛ اتصال LDAP را بررسی نمی‌کند.

برای دریافت اطلاعات باید به شبکهٔ سازمان یا VPN مربوط متصل باشید.
فایل دیتابیس پیش‌فرض `ldap_users.db` کنار main.py ساخته می‌شود.

## ساختار

- `main.py`: راه‌اندازی برنامه، جدول‌ها و روتر.
- `config.py`: تنظیمات محیطی.
- `database.py`: engine و session مربوط به SQLAlchemy.
- `models/data_model.py`: مدل جدول کاربران.
- `schemas/data_schema.py`: ساختار خروجی API.
- `services/data_service.py`: اتصال LDAP، صفحه‌بندی و همگام‌سازی.
- `routers/data_router.py`: مسیرهای API و بررسی کلید دسترسی.

فیلد uid از نوع UUID است و به objectGUID نگاشت می‌شود. نام و نام خانوادگی
می‌توانند کوتاه یا خالی باشند؛ محدودیت حداقل چهار کاراکتر حذف شده است.
فیلد مبهم attribute با فیلدهای مشخص LDAP جایگزین شده است.
نام OU تضمین فعال بودن حساب نیست؛ enabled از userAccountControl خوانده می‌شود.

همگام‌سازی یک تراکنش است: اگر یک صفحه خطا دهد، تغییرات آن اجرا برگردانده می‌شوند.
کاربری که در دریافت بعدی وجود ندارد حذف نمی‌شود؛ last_seen_at آخرین مشاهده را نشان می‌دهد.
همگام‌سازی خودکار زمان‌بندی نشده است. به دلیل قفل محلی، تنها یک worker/instance اجرا کنید.

پروتکل فعلی LDAP روی پورت 389 بدون TLS است. اگر سرور StartTLS دارد،
LDAP_START_TLS را true کنید. در صورت نیاز، مسیر گواهی CA داخلی را در
LDAP_CA_FILE بگذارید و LDAP_HOST را مطابق نام گواهی سرور تنظیم کنید.
اعتبارسنجی گواهی غیرفعال نمی‌شود. برای دسترسی از راه دور به API از HTTPS استفاده کنید.

## تست بدون شبکه

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

تست‌ها با دیتابیس حافظه‌ای و LDAP شبیه‌سازی‌شده اجرا می‌شوند.
