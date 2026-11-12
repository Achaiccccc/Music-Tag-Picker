FROM python:3.12-alpine

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py app_http.py library.py sources.py tags.py index.html .

ENV PORT=8080
ENV MUSIC_ROOT=/music
EXPOSE 8080

CMD ["python", "-u", "app.py"]
