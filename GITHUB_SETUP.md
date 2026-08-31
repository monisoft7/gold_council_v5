# رفع المشروع إلى GitHub — خطوات مضمونة

## الخيار 1: أنت ترفع (الأكثر أماناً — موصى به)

```bash
cd "gold_council"
git init
git add .
git commit -m "Initial Gold Council research platform"
# أنشئ مستودعاً فارغاً من github.com/new ثم:
git remote add origin https://github.com/USERNAME/gold-council.git
git branch -M main
git push -u origin main
```

أو بأداة GitHub الرسمية:
```bash
gh auth login
gh repo create gold-council --private --source=. --push
```

> ⚠ ملف `.env` مستثنى تلقائياً عبر `.gitignore` — تحقق قبل الرفع: `git status` يجب ألا يُظهر `.env`.

## الرفع الآمن

استخدم `gh auth login` على جهازك. لا ترسل Personal Access Token داخل المحادثة
ولا تضعه في `.env`. بعد نجاح المصادقة يمكن تنفيذ أمر `gh repo create` أعلاه.

## بعد الرفع
- Actions → سترى CI يعمل تلقائياً عند كل push (pytest + فحص الصياغة)
- أضف وصف المستودع: "Multi-agent AI council for XAU/USD recommendations — 9 agents + ML gate + walk-forward validation"
