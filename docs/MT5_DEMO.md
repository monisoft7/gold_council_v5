# تشغيل تجربة MT5 Demo

الجسر مصمم لحساب تجريبي فقط. يرفض `ACCOUNT_TRADE_MODE_REAL` برمجياً،
ويبدأ دائماً في وضع Dry Run. حتى عند تمرير `--execute-demo` لا يرسل أمراً
إلا إذا نجح تقرير الترقية discovery/holdout/forward؛ غياب التقرير يعني الحظر.

## الإعداد مرة واحدة

1. افتح MetaTrader 5 وأنشئ حساب Demo لدى الوسيط المطلوب.
2. فعّل Algo Trading داخل الطرفية.
3. انسخ `.env.example` إلى `.env` وأدخل محلياً:

```ini
MT5_LOGIN=رقم_الحساب_التجريبي
MT5_PASSWORD=كلمة_مرور_الحساب
MT5_SERVER=اسم_خادم_Demo_كما_يظهر_في_MT5
MT5_SYMBOL=XAUUSD
MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
RISK_PCT=0.25
```

قد يسمي الوسيط الذهب `XAUUSD.a` أو `GOLD`. يحاول الجسر اكتشاف الاسم تلقائياً
إذا لم يوجد `XAUUSD` حرفياً.

## الاختبار قبل الإرسال

```powershell
py -3 -X utf8 mt5_demo_service.py
```

هذا الأمر يتصل بالحساب، يتحقق أنه Demo، يقرأ الشموع المغلقة، يشغّل المجلس،
وينفذ `order_check` فقط. لا يرسل صفقة.

## تفعيل أوامر الديمو

ولّد تقرير الترقية أولاً من إعادة تشغيل MT5 المطابقة للتنفيذ:

```powershell
py -3 strategy_promotion.py `
  --discovery data_cache/mt5_native_discovery_2023_2024.json `
  --holdout data_cache/mt5_native_holdout_2025.json `
  --forward data_cache/mt5_native_forward_2025_10_2026_09.json `
  --forward-decisions data_cache/mt5_native_forward_2025_10_2026_09.csv
```

إذا كانت `promotion_allowed=false` يبقى الأمر التالي Shadow مهما طُلب التنفيذ:

```powershell
py -3 -X utf8 mt5_demo_service.py --execute-demo
```

تشغيل مستمر مرة يومياً:

```powershell
py -3 -X utf8 mt5_demo_service.py --execute-demo --loop --interval-min 1440
```

الوضع الآمن الحالي الذي يسجل المجلس ولا يرسل أوامر:

```powershell
py -3 -X utf8 mt5_demo_service.py --loop --interval-min 1440
```

لا يفتح الجسر مركزاً جديداً إذا كان هناك مركز قائم على رمز الذهب. ويستبعد
شمعة اليوم غير المكتملة حتى يطابق التنفيذ التاريخي: قرار بعد الإغلاق، ثم
دخول بالسعر الحالي للجلسة التالية.

## تقرير أسبوعين أو شهر

```powershell
py -3 -X utf8 mt5_demo_report.py --days 14
py -3 -X utf8 mt5_demo_report.py --days 30
```

يعرض التقرير عدد المراكز المغلقة، نسبة النجاح، الربح الصافي بعد العمولة
والـswap، عامل الربح، وأقصى تراجع نقدي.

## شرط التفكير في حساب حقيقي

لا يكفي مرور أسبوعين زمنياً. يلزم 30 يوماً و30 صفقة مستقلة، عامل ربح لا يقل
عن 1.25 بعد كل التكاليف، تراجع ضمن الحد، وعدم وجود أخطاء تنفيذ أو اختلاف بين
الإشارة والأمر. المشروع الحالي لا يحقق هذا الشرط تاريخياً.
