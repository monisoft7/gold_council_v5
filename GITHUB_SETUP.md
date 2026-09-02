# رفع المشروع إلى GitHub — خطوات مضمونة

## مستودع خاص — موصى به

```powershell
cd "C:\Users\THE BLU WALF\Desktop\gold_council_v8_events\gold_council_v5"
# أنشئ مستودعاً خاصاً فارغاً من github.com/new ثم:
git remote add origin https://github.com/USERNAME/gold-council.git
git push -u origin main
```

أو بأداة GitHub الرسمية:
```powershell
gh auth login -h github.com
gh repo create gold-council --private --source=. --remote=origin --push
```

> ⚠ ملف `.env` و`data_cache/` مستثنيان. لا تستخدم خيار `--public` لأن وصف
> المشروع ونتائجه لا يمثلان منتجاً مالياً معتمداً.

## الرفع الآمن

استخدم `gh auth login` على جهازك. لا ترسل Personal Access Token داخل المحادثة
ولا تضعه في `.env`. بعد نجاح المصادقة يمكن تنفيذ أمر `gh repo create` أعلاه.

## بعد الرفع
- Actions → سترى CI يعمل تلقائياً عند كل push (pytest + فحص الصياغة)
- أضف الوصف: "Research-only multi-agent XAU/USD council with causal replay and MT5 Demo safeguards"
