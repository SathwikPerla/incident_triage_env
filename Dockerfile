FROM python:3.10-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

COPY . .

ENV PYTHONPATH=/app

EXPOSE 7860

CMD ["uv", "run", "server"]