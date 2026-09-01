# 🏆 مجلس الذهب — Gold Council Research

منصة بحث كمي لـXAU/USD: وكلاء متخصصون مستقلون + رئيس مجلس + بوابة اتجاه Long/Flat + بيانات Point-in-Time. النظام في وضع `research_only` وغير معتمد للتداول الحقيقي.

## التشغيل السريع

```bash
pip install -r requirements.txt
# انسخ .env.example إلى .env ثم أدخل مفاتيحك محلياً
streamlit run app_v2.py            # الواجهة
python scheduler_service.py        # خدمة 24/7 مع تيليجرام
python mt5_demo_service.py          # MT5 Demo Dry Run — لا يرسل أمراً
python mt5_demo_service.py --execute-demo  # إرسال صريح إلى DEMO فقط
python build_economic_calendar.py --high-impact-only  # لقطة Actual/Forecast زمنية
python mt5_event_history.py --events data_cache/economic_surprises_2020_2025.csv --start 2020-01-01 --end 2025-10-01 --timeframe M15 --bars-before 16 --bars-after 120 --output data_cache/mt5_event_bars_m15_2020_2025.csv --audit-output data_cache/mt5_event_bars_m15_2020_2025_audit.json
python numeric_surprise_audit.py --surprises data_cache/economic_surprises_2020_2025.csv --bars data_cache/mt5_event_bars_m15_2020_2025.csv --timeframe-minutes 15 --split-date 2023-01-01
python economic_event_strategy.py   # باكتيست دخول M15 + وقف ATR + خروج 4h
python economic_event_shadow.py     # NFP Shadow فقط؛ لا يبني ولا يرسل أمراً
python backtester_v5.py --replay --days 720 --step 2 --aggregation-mode family --prices-csv data_cache/gold_daily_2008_2026.csv --macro-csv data_cache/macro_point_in_time_2008_2026.csv --events-csv data_cache/events_2008_2026.csv --news-csv gold_news_master.csv --out bt.json --features-out features_v5.csv
python ml_trainer.py --features features_v5.csv --model-out model.pkl --features-out feat_names.json
python walk_forward.py --features features_v5.csv   # التحقق خارج العينة
pytest -q tests/                   # الاختبارات (بدون شبكة)
```

## البنية

| الملف | الدور |
|---|---|
| `decision_pipeline.py` | مسار القرار الموحد للواجهة والجدولة والباكتيست |
| `app_v2.py` | واجهة Streamlit (اجتماع لحظي + ML Lab + دليل) |
| `agents.py` | 4 وكلاء أساسيون (أخبار/اقتصاد كلي/فني/مخاطر) |
| `cross_asset_agent.py` `seasonality_agent.py` `event_calendar_agent.py` `pattern_agent.py` | 4 وكلاء إضافيون |
| `council.py` | رئيس المجلس (تصويت حسب عائلة الدليل + فلتر اتجاه + LLM اختياري) |
| `llm_gateway.py` | Gemini/Groq/B.AI/OpenRouter ثم الاحتياطيات مع failover ومهلة صارمة |
| `alpha_vantage_news.py` | جامع NEWS_SENTIMENT تاريخي آمن كمصدر ماكرو مساعد |
| `build_news_history.py` | جامع GDELT تاريخي قابل للاستئناف لأخبار الذهب السببية |
| `build_news_events.py` | يحول الأخبار اليومية إلى أحداث منظمة ويحفظ زمن توفرها |
| `news_impact_agent.py` | وكيل أثر الأخبار Point-in-Time تجريبي بوزن صفر |
| `economic_surprise_agent.py` | وكيل Actual مقابل Consensus سببي وتجريبي بوزن صفر |
| `build_economic_calendar.py` | جامع أسبوعي append-only؛ وقت Actual هو وقت الجلب الحقيقي |
| `import_global_economic_calendar.py` | مستورد بحثي لمجموعة CC BY-NC-SA مع وسم افتراض الإتاحة |
| `mt5_event_history.py` | قارئ شموع MT5 حول الخبر؛ DEMO فقط ولا يحتوي دالة أوامر |
| `numeric_surprise_audit.py` | تدقيق زمني واتساق سنوي وتحمّل تكلفة للمفاجأة الرقمية |
| `economic_event_strategy.py` | استراتيجية أحداث كاملة: M15/ATR/4h/تكلفة/حجم 0.25% |
| `economic_event_shadow.py` | متابعة NFP 2026 بسجل append-only ومن دون تنفيذ MT5 |
| `news_timing_model.py` | مرشح محلي تجريبي يميز وصف الماضي من المعلومة المستقبلية |
| `official_event_news_sample.py` | عينة CPI/NFP/FOMC متوازنة مع checkpoint وتحليل مزود ثابت |
| `chronos_foundation_agent.py` | وكيل Chronos جاهز تجريبي بوزن صفر |
| `chronos_model_audit.py` | تدقيق زمني مستقل للنموذج التأسيسي قبل التصويت |
| `ml_overlay.py` | بوابة تجريبية غير مفعلة؛ لا تُعتمد قبل 100 صف مستقل |
| `risk_engine.py` | حجم الصفقة، Kelly/4، مستويات ATR، قاطع الأمان، حارس الارتباط |
| `walk_forward.py` | التحقق المتدحرج خارج العينة (بديل LOO) |
| `metrics.py` | Sharpe/Sortino/Calmar/MaxDD/PF/Expectancy |
| `scheduler_service.py` | اجتماع كل N دقيقة + إشعار تيليجرام |
| `paper_journal.py` | سجل JSONL غير قابل لإعادة كتابة القرارات السابقة |
| `env_loader.py` | قراءة .env متسامحة (BOM/CRLF/اقتباسات/أسماء بديلة) |
| `backtester_v5.py` | باك-تست مُصحَّح (SL/TP فعليان، لا تلاعب بالنافذة) |
| `ml_trainer.py` | تدريب XGBoost (TSS ≥30 صفاً / LOO ≥15) |
| `news_classifier.py` | تصنيف الأخبار 7 فئات + Groq اختياري |
| `mt5_demo_bridge.py` | جسر MT5 يرفض الحساب الحقيقي ويفحص الطلب قبل إرساله |
| `mt5_demo_service.py` | تشغيل المجلس على شموع MT5 المغلقة وتنفيذ Demo اختياري |
| `mt5_demo_report.py` | تقرير نتائج 14/30 يوماً من سجل صفقات MT5 |
| `tests/` | اختبارات تعمل بدون إنترنت، بينها منع تسرب المستقبل وMT5 وLLM failover |
| `.github/workflows/ci.yml` | CI عند كل push |

## المقارنة المعيارية مع أفضل المشاريع المفتوحة

| المعيار | Freqtrade | Jesse | TradingAgents | **مجلس الذهب** |
|---|---|---|---|---|
| استراتيجيات قابلة للاستبدال | ✅ | ✅ | ➖ | ✅ (وكلاء معيارية) |
| باك-تست بدون look-ahead | ✅ | ✅ | ⚠ | ✅ (نافذة ≥5 أيام) |
| Walk-Forward مدمج | ➖ | ✅ | ❌ | ✅ |
| وكلاء تحليل متعددون | ❌ | ❌ | ✅ | ✅ (وكلاء أسر دليل مستقلة) |
| بوابة ML فوق الإشارة | ➖ | ➖ | ❌ | 🧪 تجريبية غير مفعلة |
| إدارة مخاطر (Kelly/ATR/DD-breaker) | ✅ | ✅ | ⚠ | ✅ |
| تيليجرام لحظي | ✅ | ➖ | ❌ | ✅ |
| اختبارات pytest + CI | ✅ | ✅ | ➖ | ✅ (offline) |
| يدعم الذهب XAU/USD مباشرة | ➖ (كريبتو) | ➖ (كريبتو) | ➖ (أسهم) | ✅ أصلي |

## ⚠ تنبيه إلزامي

هذا النظام أداة تحليل ومساعد قرار — **ليس توصية مالية ولا بديلاً عن حكمك**. النتائج التاريخية (باك-تست) لا تضمن الأداء المستقبلي. جرّب على حساب تجريبي 3-6 أشهر قبل أي مال حقيقي.
