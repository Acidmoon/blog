FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV BLOG_SECRET_KEY="change-me-to-a-secure-random-key"
ENV BLOG_ADMIN_PASSWORD="admin123"

EXPOSE 8082

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8082", "app:app"]
