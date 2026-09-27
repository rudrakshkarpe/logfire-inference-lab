FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN pip install --no-cache-dir uv && uv sync --locked --no-dev --no-editable
RUN useradd --create-home observatory && mkdir -p /app/data && chown -R observatory:observatory /app
USER observatory
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8877
CMD ["observatory", "serve", "--host", "0.0.0.0"]
