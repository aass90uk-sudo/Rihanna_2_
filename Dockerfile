FROM python:3.11-slim

WORKDIR /app

# نسخ ملف المكتبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ بقية ملفات المشروع
COPY . .

# أمر تشغيل البوت
CMD ["python", "main.py"]
