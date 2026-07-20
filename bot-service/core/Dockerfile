FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY src/ src/

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "bot_core.main:app", "--host", "0.0.0.0", "--port", "8000"]