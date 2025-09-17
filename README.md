
# Balanced & Flexible DOGE Bot Pack — 24/7 on Render

## ماذا يقدّم
- **استراتيجية مرنة** (balanced) مع كل الحمايات ضد عكس الاتجاه.
- **Logging احترافي**:
  - Snapshot للمؤشرات قبل كل محاولة دخول.
  - أسباب عدم الدخول (`🚫 NO-TRADE: ...`).
  - تفاصيل كاملة عند فتح الصفقة (BUY/SELL, qty, entry, TP, SL, price, ATR, ADX, RSI).
  - طباعة الربح التراكمي بعد كل إغلاق.
- **Leverage 10x** + **60% من الرصيد** لكل صفقة (من دون لمس الدوال الأساسية).
- **Keep-Alive** كل دقيقة لضمان 24/7.

## الاستخدام
- ارفع هذه الملفات بجانب `bot.py` (أو عرّف `BOT_MODULE`).
- Env Vars الأساسية: `BINGX_API_KEY`, `BINGX_API_SECRET`, (اختياري) `PUBLIC_URL`, `BINGX_BASE_URL`.
- Start Command:
  ```bash
  gunicorn -w 1 -b 0.0.0.0:$PORT runner:app
  ```
