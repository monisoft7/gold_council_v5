# -*- coding: utf-8 -*-
"""واجهة منصة مجلس الذهب البحثية: اجتماع حي + مختبر ML.

تستخدم env_loader المُوحَّد لقراءة المفاتيح، ودالة data_feeds.collect_all()
التي تشمل get_spot_price + get_ohlc + get_news.
"""
import os
import streamlit as st
import plotly.graph_objects as go

try:
    import config  # اختياري — يستخدمه env_loader.load_env إن وُجد
    try:
        config.load_env()
    except Exception:
        pass
except Exception:
    config = None

from env_loader import env  # الـloader الموحَّد الجديد
import data_feeds
import indicators
import agents
import council
import telegram_notifier as tg
import decision_pipeline
from build_economic_calendar import update_snapshot as update_economic_calendar
import paper_journal
try:
    from news_classifier import CATEGORIES, HIGH_IMPACT
except Exception:
    CATEGORIES, HIGH_IMPACT = {}, []

# === إعدادات الصفحة ===
st.set_page_config(
    page_title="مجلس الذهب — Research",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.session_state.setdefault("last_run", None)
st.session_state.setdefault("last_dec_text", None)


# === الشريط الجانبي ===
with st.sidebar:
    st.title("⚙ إعدادات الجلسه")
    capital = st.number_input("رأس المال (ر.أ)", 100.0, 1_000_000.0, 10_000.0, step=1000.0)
    risk_pct = st.slider("مخاطرة لكل صفقة %", 0.1, 5.0, 1.0, 0.1)
    st.divider()
    st.subheader("📡 تيليجرام")
    # دعم كل اصطلاحات التسمية
    tg_token = st.text_input("Bot Token",
                             value=env.get("TELEGRAM_BOT_TOKEN"),
                             type="password",
                             help="توكن @BotFather (يدعم TG_TOKEN أو TELEGRAM_BOT_TOKEN)")
    tg_chat = st.text_input("Chat ID",
                            value=env.get("TELEGRAM_CHAT_ID"),
                            help="ID محادثتك (يدعم TG_CHAT_ID أو TELEGRAM_CHAT_ID)")
    tg_mode = st.selectbox("وضع الإرسال", ["كل قرار", "فقط تغيير القرار"], index=0)
    st.divider()
    with st.expander("🔑 تشخيص .env"):  # مرئي للتشخيص فقط
        st.json(env.debug_masked())
        if env.path:
            st.caption(f"📁 مسار .env المُحمَّل: `{env.path}`")
        else:
            st.warning("لم يُعثر على ملف .env")
    st.divider()
    with st.expander("🔑 مفاتيح LLM (اختياري)"):
        llm_key = st.text_input("OPENAI_API_KEY",
                                value=env.get("OPENAI_API_KEY"),
                                type="password")
        llm_url = st.text_input("OPENAI_BASE_URL",
                                value=env.get("OPENAI_BASE_URL",
                                              "https://api.groq.com/openai/v1"))
        llm_model = st.text_input("Model",
                                  value=env.get("OPENAI_MODEL",
                                                "llama-3.3-70b-versatile"))


st.title("🏆 مجلس الذهب — Gold Council Research")
st.caption("وكلاء متخصصون وبوابات اتجاه ومخاطر | بيانات حية + ماكرو وCOT مؤرخان زمنياً")


def run_agents(spot, daily, news):
    """تشغيل مسار القرار الموحد وعرض أخطائه بوضوح."""
    calendar_warning = None
    try:
        try:
            update_economic_calendar(high_impact_only=True)
            decision_pipeline.clear_data_caches()
        except Exception as exc:
            calendar_warning = f"تعذر تحديث التقويم الرقمي؛ استُخدمت آخر لقطة محلية: {exc}"
        result = decision_pipeline.run_decision(
            daily, news, spot_price=spot.get("price"),
            capital=capital, risk_pct=risk_pct,
            load_cached_macro=True,
            load_cached_surprises=True,
        )
    except Exception as exc:
        st.error(f"فشل تجميع الوكلاء: {exc}")
        return None
    for warning in result["dec"].get("pipeline_warnings", []):
        st.warning(warning)
    if calendar_warning:
        st.warning(calendar_warning)
    return result["reports"], result["dec"], result["last_price"]


# === التبويبات ===
tab_live, tab_ml, tab_doc = st.tabs(["🟢 اجتماع لحظي", "🧪 مختبر التعلم العميق", "📖 الدليل"])

# --- تبويب 1: الاجتماع اللحظي ---
with tab_live:
    if st.button("🔄 عقد اجتماع الآن", type="primary"):
        with st.spinner("جمع البيانات من الإنترنت..."):
            try:
                spot, daily, intra, news = data_feeds.collect_all()
                st.session_state["last_run"] = (spot, daily, intra, news)
            except Exception as exc:
                st.error(f"تعذّر جلب البيانات: {exc}")
                spot = daily = intra = news = None

        if st.session_state.get("last_run"):
            spot, daily, intra, news = st.session_state["last_run"]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("السعر اللحظي", f"${spot['price']:,.2f}" if spot['price'] else "—",
                        f"{spot.get('change_pct', 0):+.2f}%")
            col2.metric("متذبذب 24س", f"{intra.iloc[-1].get('atr', 0):.2f}" if not intra.empty else "—")
            col3.metric("عدد الأخبار", f"{len(news)}")
            col4.metric("رأس المال", f"${capital:,.0f}")

            result = run_agents(spot, daily, news)
            if result:
                reports, dec, last = result
                journal_result = {
                    "dec": dec, "reports": reports, "last_price": last, "news": news,
                }
                record = paper_journal.append_record(journal_result)
                st.caption(f"سُجل الاجتماع ورقياً: {record['run_id']}")

                st.divider()
                st.subheader("📊 توصية رئيس المجلس")
                emoji_map = {"شراء قوي": "🟢🟢", "شراء": "🟢", "محايد": "🟡",
                             "بيع": "🔴", "بيع قوي": "🔴🔴"}
                col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                col_r1.markdown(f"### {emoji_map.get(dec['decision'], '⚪')} {dec['decision']}")
                col_r2.metric("الدرجة", f"{dec['final_score']:.1f}", "-100..+100")
                col_r3.metric("الثقة", f"{dec['confidence']:.0f}%")
                col_r4.metric("إجماع", f"{dec.get('agreement', 0):.0f}%")
                if dec.get("research_only"):
                    st.warning("وضع بحثي غير معتمد للتداول الحقيقي؛ الثقة مقيدة حتى نجاح اختبار مستقل.")
                if dec.get("risk_multiplier", 1.0) < 1.0:
                    st.info(f"معامل المخاطرة الحالي: {dec['risk_multiplier']:.0%}")
                size_cols = st.columns(3)
                size_cols[0].metric("التعرض الفعلي", f"{dec.get('exposure_pct', 0):.0f}%")
                size_cols[1].metric("الحجم المقترح", f"{dec.get('position_oz', 0):.4f} أونصة")
                size_cols[2].metric("ميزانية المخاطرة", f"${dec.get('risk_budget_usd', 0):,.2f}")

                lv = dec.get("levels") or {}
                def _fmt(x):
                    return f"{x:,.2f}" if isinstance(x, (int, float)) else "—"
                if lv:
                    st.markdown(f"**دخول** {_fmt(lv.get('entry'))} | "
                                f"**وقف** {_fmt(lv.get('sl'))} | "
                                f"**هدف1** {_fmt(lv.get('tp1'))} | "
                                f"**هدف2** {_fmt(lv.get('tp2'))}")
                else:
                    st.caption("لا مستويات سعرية لهذا القرار (محايد/انتظار)")

                # إرسال تيليجرام
                should_notify = (
                    tg_mode == "كل قرار"
                    or st.session_state.get("last_dec_text") != dec["decision"]
                )
                if tg_token and tg_chat and should_notify:
                    try:
                        h_titles = [n["title"] for n in news[:4]]
                        ok, msg = tg.send_telegram(
                            tg_token, tg_chat,
                            tg.build_signal_message(dec, last, reports, h_titles))
                        toast_text = f"{'تم الإرسال' if ok else 'فشل الإرسال'}: {msg}"
                        st.toast(toast_text, icon="✅" if ok else "⚠")
                        st.session_state["last_dec_text"] = dec["decision"]
                    except Exception as e:
                        st.warning(f"تيليجرام: {e}")

                # عرض تقارير الوكلاء
                st.divider()
                st.subheader("🤖 تقارير الوكلاء")
                tabs_per_agent = st.tabs([f"{r.icon} {r.name}" for r in reports])
                for tab_one, r in zip(tabs_per_agent, reports):
                    with tab_one:
                        st.markdown(f"**{r.role}**")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("الدرجة", f"{r.score:+.1f}")
                        c2.metric("الثقة", f"{r.confidence:.0f}%")
                        c3.metric("وزن", f"{getattr(r, 'weight', 1.0):.1f}x")
                        with st.expander("النقاط", expanded=False):
                            for b in r.bullets:
                                st.markdown(f"- {b}")

                # رسم السعر
                st.divider()
                st.subheader("📈 الشارت اللحظي (ساعة)")
                if not intra.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=intra["time"], open=intra["open"], high=intra["high"],
                        low=intra["low"], close=intra["close"], name="السعر"))
                    lv = dec.get("levels") or {}
                    for label, v in lv.items():
                        try:
                            v = float(v)          # بعض المستويات قد تأتي نصاً/None
                        except (TypeError, ValueError):
                            continue              # تخطَّ أي مستوى غير رقمي
                        fig.add_hline(y=v, line_dash="dash",
                                      annotation_text=str(label))
                    fig.update_layout(height=400, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, width="stretch")

# --- تبويب 2: مختبر التعلم العميق ---
with tab_ml:
    st.subheader("🧪 مختبر التعلم الآلي (ML Lab)")
    st.markdown("يشغّل الباكتيست الموحد ثم يسمح بتدريب XGBoost/GradientBoosting "
                "فقط عند توفر 100 صف مستقل على الأقل.")

    col_a, col_b = st.columns(2)
    days_back = col_a.selectbox("المدة بأيام", [180, 365, 540, 720, 1080], index=2)
    step_days = col_b.selectbox("فاصل اجتماع (يوم)",
                                [2, 3, 4, 5, 7, 10], index=0)
    prices_csv = st.text_input("مسار ملف CSV للأسعار (اتركه فارغاً = جلب Yahoo)",
                               value="data_cache/gold_daily_2008_2026.csv")
    news_csv = st.text_input("مسار ملف CSV للأخبار (time,title,source,section)",
                             value="gold_news_master.csv")
    out_json = st.text_input("مسار تقرير الباك-تست", value="data_cache/council_bt_ui.json")
    out_features = st.text_input("مسار ملف المزايا", value="data_cache/council_features_ui.csv")
    out_model = st.text_input("مسار النموذج (.pkl)", value="model.pkl")
    out_names = st.text_input("مسار أسماء المزايا", value="feat_names.json")

    if st.button("① تشغيل الباكتيست ثم تقييم أهلية ML", type="primary"):
        import subprocess, sys, os as _os
        cmd = [sys.executable, "backtester_v5.py", "--replay",
               "--days", str(days_back), "--step", str(step_days),
               "--news-csv", news_csv, "--out", out_json,
               "--features-out", out_features,
               "--macro-csv", "data_cache/macro_point_in_time_2008_2026.csv",
               "--events-csv", "data_cache/events_2008_2026.csv"]
        if prices_csv.strip():
            cmd += ["--prices-csv", prices_csv.strip()]
        with st.spinner(f"باك-تست V5 على {days_back} يوم بفاصل {step_days}..."):
            run1 = subprocess.run(cmd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        st.code(run1.stdout[-1500:] if run1.stdout else "(no stdout)", language="text")
        if run1.stderr:
            st.error("STDERR: " + run1.stderr[-800:])

        if run1.returncode == 0 and _os.path.exists(out_features):
            cmd2 = [sys.executable, "ml_trainer.py", "--features", out_features,
                    "--model-out", out_model, "--features-out", out_names]
            with st.spinner("تدريب نموذج التعلم العميق..."):
                run2 = subprocess.run(cmd2, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            st.code(run2.stdout[-1500:] if run2.stdout else "(no stdout)", language="text")
            if run2.stderr:
                st.error("STDERR train: " + run2.stderr[-800:])

            if run2.returncode == 0 and '"status": "ok"' in run2.stdout:
                st.success(f"✅ تم بناء النموذج في {out_model}")
            else:
                st.warning("⚠ لم يُبن نموذج جديد؛ غالباً العينة دون 100 صف مستقل. النموذج القديم—إن وجد—لم يُعتمد.")

# --- تبويب 3: الدليل ---
with tab_doc:
    st.markdown("""
    ## طريقة الاستخدام
    1. **تبويب اجتماع لحظي**: اضغط زر "عقد اجتماع الآن" لاستدعاء 12 وكيلاً.
    2. **تبويب ML Lab**: حدد المدة ثم اضغط زر تدريب.
    3. **تيليجرام**: ضع Token و Chat ID في الشريط الجانبي أو في `.env`.

    ## المفتاح في ملف .env (يدعم اسمين لكل واحد)
    ```ini
    TG_TOKEN=123456:ABC                  # أو TELEGRAM_BOT_TOKEN
    TG_CHAT_ID=-1001234567890             # أو TELEGRAM_CHAT_ID
    OPENAI_API_KEY=gsk_xxx                # أو GROQ_API_KEY
    OPENAI_BASE_URL=https://api.groq.com/openai/v1
    OPENAI_MODEL=llama-3.3-70b-versatile
    ```

    ## الأوامر السريعة
    ```
    python backtester_v5.py --replay --days 540 --step 2 ^
        --news-csv gold_news_master.csv ^
        --macro-csv data_cache/macro_point_in_time_2008_2026.csv ^
        --events-csv data_cache/events_2008_2026.csv ^
        --out bt_v5_corr.json ^
        --features-out features_v5.csv

    python ml_trainer.py --features features_v5.csv ^
        --model-out model.pkl ^
        --features-out feat_names.json

    streamlit run app_v2.py
    ```
    """)
