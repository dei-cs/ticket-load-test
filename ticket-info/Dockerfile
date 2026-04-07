FROM python:3.12

WORKDIR /app


COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project

COPY main.py ./

CMD ["uv", "run", "main.py"]
