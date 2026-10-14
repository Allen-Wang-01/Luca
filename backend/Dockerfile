# The backend as deployed (fly.toml). Development runs it straight from the virtualenv
# with `python start.py` instead; see CLAUDE.md.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Everything .dockerignore doesn't leave out: the app, and the saved demos if there are any.
COPY . .

EXPOSE 8080
# One process: the narration stream runs each agent on its own thread, and nothing is
# kept between requests, so there is no state for several workers to share.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
